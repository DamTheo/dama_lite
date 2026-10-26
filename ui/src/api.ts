import type { MachineStatus, TestStatus } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) {
    let detail = "HTTP " + response.status;
    try {
      const body = await response.json() as { error?: string };
      detail = body.error || detail;
    } catch { /* Format d'erreur non JSON. */ }
    throw new Error(detail);
  }
  return await response.json() as T;
}

export function getStatus(): Promise<MachineStatus> {
  return request<MachineStatus>("/api/status");
}

/** Sélection éphémère de la caméra pendant la préparation d'une analyse. */
export function selectCameraForSetup(camera: number | null): Promise<{ selected: number | null }> {
  return request("/api/selection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera }),
  });
}

export function startTest(camera: number, name: string): Promise<{ test: TestStatus }> {
  return request("/api/tests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera, name }),
  });
}

export function stopTest(id: string): Promise<{ ok: boolean }> {
  return request("/api/tests/" + encodeURIComponent(id) + "/stop", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
}

export function acknowledgeCamera(slot: number): Promise<{ ok: boolean }> {
  return request("/api/cameras/" + slot + "/ack", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
}

export function streamUrl(slot: number, moment: number): string {
  return "/api/cameras/" + slot + "/stream?t=" + moment;
}
