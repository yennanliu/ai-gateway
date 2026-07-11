export type Tone = "healthy" | "degraded" | "down";

export interface HealthDisplay {
  label: string;
  tone: Tone;
}

/** Map a raw health status string to a display label + tone. */
export function healthDisplay(status: string): HealthDisplay {
  switch (status.toLowerCase()) {
    case "ok":
    case "ready":
    case "healthy":
      return { label: "Healthy", tone: "healthy" };
    case "degraded":
      return { label: "Degraded", tone: "degraded" };
    default:
      return { label: "Down", tone: "down" };
  }
}
