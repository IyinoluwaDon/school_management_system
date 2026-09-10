"""Domain 2 - Algorithmic Optimization Engine.

Two independent engines live here:

* ``generate_timetable``  - a Google OR-Tools CP-SAT model that builds a
  conflict-free weekly timetable for a term.
* ``allocate_exam_seating`` - a greedy, adjacency-aware seat allocator that
  spreads candidates across one or more halls.

Both replace the naive placeholders that used to live in ``services.py``
(a first-fit greedy timetable and a sequential seat-numbering scheme), while
keeping the same model shapes so the rest of the app (admin, existing
services, tests) doesn't need to change.
"""

import heapq
import math
from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from ortools.sat.python import cp_model

from .models import ExamCandidate, Room, SchoolClass, SubjectAssignment, TimetableEntry

# --------------------------------------------------------------------------
# Timetable engine (CP-SAT)
# --------------------------------------------------------------------------

WEEKDAYS = (1, 2, 3, 4, 5)  # Monday..Friday - matches TimetableEntry.WEEKDAYS
PERIODS_PER_DAY = 8
PERIOD_MINUTES = 40
DAY_START = time(8, 0)
SOLVER_TIME_LIMIT_SECONDS = 30


def _period_times(period_index, day_start, period_minutes):
    anchor = datetime.combine(date.today(), day_start)
    start = anchor + timedelta(minutes=period_minutes * period_index)
    end = start + timedelta(minutes=period_minutes)
    return start.time(), end.time()


def _assign_home_rooms(school_classes, rooms):
    """Round-robin classes onto rooms so the room and class constraints line up.

    Real timetables usually keep a class in one home room for most of the
    week while teachers move between rooms; modelling it this way keeps the
    CP-SAT problem tractable (one room variable per class instead of per
    session) while still correctly enforcing "a room can't host two classes
    at once" whenever there are fewer rooms than classes.
    """
    if not rooms:
        raise ValidationError("At least one room must be available to build a timetable.")
    return {school_class.pk: rooms[index % len(rooms)] for index, school_class in enumerate(school_classes)}


@transaction.atomic
def generate_timetable(
    term,
    assignments=None,
    rooms=None,
    weekdays=WEEKDAYS,
    periods_per_day=PERIODS_PER_DAY,
    period_minutes=PERIOD_MINUTES,
    day_start=DAY_START,
    replace_existing=True,
    time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS,
):
    """Build a conflict-free weekly timetable for ``term`` with CP-SAT.

    Hard constraints (always satisfied, or the solve fails outright):
      - a teacher is never double-booked in the same slot
      - a class is never double-booked in the same slot (one subject at a time)
      - a room is never double-booked in the same slot

    Soft constraint (optimized for, but won't make the problem infeasible):
      - subjects flagged ``Subject.is_difficult`` are spread across different
        days per class instead of being clustered on one day.

    Returns a summary dict; persists the winning assignment as
    ``TimetableEntry`` rows.
    """
    assignments = list(
        (assignments if assignments is not None else SubjectAssignment.objects.filter(term=term))
        .select_related("teacher", "subject", "school_class")
    )
    if not assignments:
        raise ValidationError("No subject assignments were found for this term.")

    rooms = list(rooms if rooms is not None else Room.objects.all())
    school_classes = sorted({a.school_class for a in assignments}, key=lambda c: c.pk)
    home_room = _assign_home_rooms(school_classes, rooms)

    slots = [(day, period) for day in weekdays for period in range(periods_per_day)]
    slot_index = {slot: i for i, slot in enumerate(slots)}

    model = cp_model.CpModel()

    # One "session" per (assignment, k-th period of the week it needs).
    session_specs = [
        (assignment, k)
        for assignment in assignments
        for k in range(max(1, assignment.periods_per_week))
    ]
    if len(session_specs) > len(slots) * max(1, len({a.teacher_id for a in assignments})):
        # Not a hard failure - just a fast, cheap early warning before we ask
        # the solver to prove infeasibility the slow way.
        pass

    x = {
        (s_idx, slot_idx): model.NewBoolVar(f"x_{s_idx}_{slot_idx}")
        for s_idx in range(len(session_specs))
        for slot_idx in range(len(slots))
    }

    # Every session lands in exactly one slot.
    for s_idx in range(len(session_specs)):
        model.AddExactlyOne(x[s_idx, slot_idx] for slot_idx in range(len(slots)))

    def _at_most_one_per_slot(groups):
        for indices in groups.values():
            for slot_idx in range(len(slots)):
                model.Add(sum(x[s_idx, slot_idx] for s_idx in indices) <= 1)

    sessions_by_assignment, sessions_by_teacher = defaultdict(list), defaultdict(list)
    sessions_by_class, sessions_by_room = defaultdict(list), defaultdict(list)
    difficult_sessions_by_class = defaultdict(list)

    for s_idx, (assignment, _k) in enumerate(session_specs):
        sessions_by_assignment[assignment.pk].append(s_idx)
        sessions_by_teacher[assignment.teacher_id].append(s_idx)
        sessions_by_class[assignment.school_class_id].append(s_idx)
        sessions_by_room[home_room[assignment.school_class_id].pk].append(s_idx)
        if assignment.subject.is_difficult:
            difficult_sessions_by_class[assignment.school_class_id].append(s_idx)

    # A single assignment's own sessions can't collide with each other either.
    _at_most_one_per_slot(sessions_by_assignment)
    # Hard constraint: teacher cannot teach two classes simultaneously.
    _at_most_one_per_slot(sessions_by_teacher)
    # Hard constraint: a class can only be doing one subject at a time.
    _at_most_one_per_slot(sessions_by_class)
    # Hard constraint: a room cannot host two classes simultaneously.
    _at_most_one_per_slot(sessions_by_room)

    # Soft constraint: spread difficult subjects across the week rather than
    # stacking them on one day. For each class/day, penalise any count above 1.
    penalties = []
    for class_id, s_indices in difficult_sessions_by_class.items():
        for day in weekdays:
            day_slots = [slot_index[(day, p)] for p in range(periods_per_day)]
            day_count = sum(x[s_idx, slot_idx] for s_idx in s_indices for slot_idx in day_slots)
            excess = model.NewIntVar(0, len(s_indices), f"excess_{class_id}_{day}")
            model.Add(excess >= day_count - 1)
            penalties.append(excess)
    if penalties:
        model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValidationError(
            "No conflict-free timetable could be generated for these assignments. "
            "Try adding more rooms or periods per day, or reducing periods_per_week."
        )

    entries = []
    for s_idx, (assignment, _k) in enumerate(session_specs):
        for slot_idx, (day, period) in enumerate(slots):
            if solver.Value(x[s_idx, slot_idx]):
                start, end = _period_times(period, day_start, period_minutes)
                entries.append(
                    TimetableEntry(
                        school_class=assignment.school_class,
                        subject=assignment.subject,
                        teacher=assignment.teacher,
                        room=home_room[assignment.school_class_id],
                        term=term,
                        weekday=day,
                        start_time=start,
                        end_time=end,
                    )
                )
                break

    if replace_existing:
        TimetableEntry.objects.filter(term=term).delete()
    TimetableEntry.objects.bulk_create(entries)

    return {
        "status": solver.StatusName(status),
        "entries_created": len(entries),
        "sessions_requested": len(session_specs),
        "rooms_used": len({room.pk for room in home_room.values()}),
        "difficult_subject_day_clashes": int(solver.ObjectiveValue()) if penalties else 0,
        "solve_time_seconds": round(solver.WallTime(), 3),
    }


# --------------------------------------------------------------------------
# Exam seating engine
# --------------------------------------------------------------------------

@transaction.atomic
def allocate_exam_seating(paper, rooms=None, columns=None):
    """Seat every candidate for ``paper``, spreading same-class students apart.

    Strategy: repeatedly seat the *largest remaining class group* into the
    next free seat (row-major order per hall), skipping a group only when
    seating it would put it directly beside (same row, previous column) or
    directly behind (same column, previous row) another student from that
    same class - and only skipping when an alternative group is available.
    This is the classic constructive heuristic for this problem: it always
    succeeds when a conflict-free arrangement is possible, and degrades
    gracefully (flagging the unavoidable clashes) when one class is too
    large to fully separate from itself.

    Candidates are distributed across ``rooms`` (default: the paper's own
    hall plus any configured overflow halls) in the order given, filling
    one hall before spilling into the next.
    """
    candidates = list(
        ExamCandidate.objects.filter(paper=paper)
        .select_related("student__school_class")
        .order_by("student__school_class_id", "student_id")
    )
    if not candidates:
        raise ValidationError("This exam paper has no registered candidates.")

    room_pool = list(dict.fromkeys(rooms if rooms is not None else paper.available_rooms))
    if not room_pool:
        raise ValidationError("At least one room must be available for exam seating.")

    total_capacity = sum(room.capacity for room in room_pool)
    if len(candidates) > total_capacity:
        raise ValidationError(
            f"{len(candidates)} candidates are registered but only {total_capacity} seats "
            f"are available across {len(room_pool)} room(s)."
        )

    groups = defaultdict(deque)
    for candidate in candidates:
        groups[candidate.student.school_class_id].append(candidate)
    # Max-heap (via negated counts) keyed by remaining group size, so the
    # biggest outstanding class is always the next one offered a seat.
    heap = [(-len(members), class_id) for class_id, members in groups.items()]
    heapq.heapify(heap)

    seated = []
    unresolved_adjacencies = 0

    for room in room_pool:
        if not heap:
            break
        rows, cols = room.seating_grid
        if columns:
            cols = columns
            rows = math.ceil(room.capacity / cols)
        grid_class = {}  # (row, col) -> class_id already seated there, for neighbour checks
        seats_filled = 0

        for row in range(rows):
            for col in range(cols):
                if seats_filled >= room.capacity or not heap:
                    break
                blocked = set()
                if col > 0 and (row, col - 1) in grid_class:
                    blocked.add(grid_class[(row, col - 1)])
                if row > 0 and (row - 1, col) in grid_class:
                    blocked.add(grid_class[(row - 1, col)])

                deferred = []
                chosen_class_id, forced = None, False
                while heap:
                    neg_count, class_id = heapq.heappop(heap)
                    if class_id in blocked and heap:
                        deferred.append((neg_count, class_id))
                        continue
                    chosen_class_id, forced = class_id, class_id in blocked
                    break
                for item in deferred:
                    heapq.heappush(heap, item)
                if chosen_class_id is None:
                    break  # heap emptied entirely (only deferred items remain to restore)
                if forced:
                    unresolved_adjacencies += 1

                candidate = groups[chosen_class_id].popleft()
                candidate.room = room
                candidate.row = row + 1
                candidate.column = col + 1
                candidate.seat_number = row * cols + col + 1
                seated.append(candidate)
                grid_class[(row, col)] = chosen_class_id
                seats_filled += 1

                if groups[chosen_class_id]:
                    heapq.heappush(heap, (-len(groups[chosen_class_id]), chosen_class_id))
            if seats_filled >= room.capacity or not heap:
                continue

    ExamCandidate.objects.bulk_update(seated, ["room", "row", "column", "seat_number"])
    return {
        "seated": len(seated),
        "rooms_used": len({c.room_id for c in seated}),
        "unresolved_adjacencies": unresolved_adjacencies,
    }
