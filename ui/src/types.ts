export type LedState = "available" | "running" | "fault" | "off";
export type Screen = "home" | "menu" | "new" | "cameras" | "camera" | "tests";

export interface ThermalStatus {
  temperature_c: number | null;
  cpu_temperature_c: number | null;
  heater_on: boolean;
  heating_enabled: boolean;
  ready: boolean;
  fault: string | null;
  cpu_warning: boolean;
  last_read_at: number | null;
}
export interface CameraStatus {
  slot: number;
  configured: boolean;
  mapping_verified: boolean;
  connected: boolean;
  led: LedState;
  health: LedState;
  active_test: string | null;
}
export interface TestStatus {
  id: string;
  name: string;
  camera_slot: number;
  state: "running" | "stopped" | "fault" | "interrupted";
  created_at: string;
  ended_at: string | null;
  images_count: number;
  pending_uploads: number;
  upload_errors: number;
  acknowledged: number;
  error: string | null;
  next_photo_seconds: number | null;
  folder_url: string | null;
}
export interface HeatTestStatus {
  gateway_ready: boolean;
  operator_armed: boolean;
  phase: string;
  active: boolean;
  result: string;
  request_pending: boolean;
  max_duration_s: number;
  max_chamber_c: number;
  last_record: null | {
    file: string;
    elapsed_s: number;
    temperature_c: number;
    cpu_c: number;
    relay_command_on: boolean;
    fault: string | null;
  };
}

export interface MachineStatus {
  power: "starting" | "on" | "shutting" | "shutdown_failed" | "shutdown_disabled" | "off";
  thermal: ThermalStatus;
  heat_test: HeatTestStatus;
  cameras: CameraStatus[];
  tests: TestStatus[];
  sharepoint_configured: boolean;
  shutdown_available: boolean;
  shutdown_confirmation_required: boolean;
  pending_uploads: number;
  ui_selected_camera: number | null;
  interval_seconds: number;
  temperature_start_min_c: number;
  setpoint_c: number;
}
