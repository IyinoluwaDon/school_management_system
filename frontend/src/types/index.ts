export type Role = "SUPER_ADMIN" | "PRINCIPAL" | "TEACHER" | "ACCOUNTANT" | "HR" | "STUDENT" | "PARENT";

// Mirrors accounts/serializers.py:serialize_user() exactly.
export interface AuthenticatedUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: Role;
  digital_token: string;
  profile_id: number | null;
  profile_type: "STUDENT" | "STAFF" | null;
  is_active: boolean;
}

export interface TokenPair {
  access: string;
  refresh: string;
  user: AuthenticatedUser;
}

export interface UserSession {
  username: string;
  displayName: string;
  role: Role;
  token?: string;
}

export interface AttendanceScanResult {
  type: "student" | "staff";
  created: boolean;
  duplicate: boolean;
  name: string;
  status: string;
  record_id: number;
  class?: string;
  department?: string;
  clock_in?: string | null;
  clock_out?: string | null;
}

export interface AttendanceRecord {
  id: number;
  student: number;
  date: string;
  status: "PRESENT" | "ABSENT" | "LATE" | "EXCUSED";
  method: string;
  notes: string;
}

export interface TimetableEntry {
  id: number;
  weekday: number;
  start: string;
  end: string;
  subject: string;
  class: string;
  class_id: number;
  teacher: string;
  room: string | null;
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  audience: string;
}

// Domain 2: scheduling engines (school/scheduling.py)
export interface GenerateTimetableResult {
  status: string;
  entries_created: number;
  sessions_requested: number;
  rooms_used: number;
  difficult_subject_day_clashes: number;
  solve_time_seconds: number;
}

export interface GenerateSeatingResult {
  seated: number;
  rooms_used: number;
  unresolved_adjacencies: number;
}

export interface SeatingSeat {
  student_id: number;
  name: string;
  admission_number: string;
  class: string;
  class_id: number;
  row: number;
  column: number;
  seat_number: number;
}

export interface SeatingHall {
  room: string;
  rows: number | null;
  columns: number | null;
  seats: SeatingSeat[];
}

export interface SeatingPlan {
  paper: { id: number; subject: string; examination: string; exam_date: string };
  halls: SeatingHall[];
}

export interface ApiError {
  error: string;
}
