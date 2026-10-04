import { BedDouble, Coffee, Flag, Fuel, Package, RotateCcw, Truck, type LucideIcon } from "lucide-react";
import type { StopType, Waypoint } from "../api/types";

export interface MarkerStyle {
  label: string;
  icon: LucideIcon;
  color: string; // marker background
  soft: string; // tinted background for lists
}

export const WAYPOINT_STYLE: Record<Waypoint, MarkerStyle> = {
  current: { label: "Current location", icon: Truck, color: "#0b3a44", soft: "#e6eff1" },
  pickup: { label: "Pickup", icon: Package, color: "#0d9488", soft: "#e2f5f3" },
  dropoff: { label: "Drop-off", icon: Flag, color: "#f2545b", soft: "#fdeced" },
};

export const STOP_STYLE: Record<StopType, MarkerStyle> = {
  start: WAYPOINT_STYLE.current,
  end: WAYPOINT_STYLE.dropoff,
  pickup: WAYPOINT_STYLE.pickup,
  dropoff: WAYPOINT_STYLE.dropoff,
  fuel: { label: "Fuel stop", icon: Fuel, color: "#d97706", soft: "#fef3e2" },
  break: { label: "30-min break", icon: Coffee, color: "#0284c7", soft: "#e4f3fb" },
  rest: { label: "10-hour rest", icon: BedDouble, color: "#6366f1", soft: "#eceefe" },
  restart: { label: "34-hour restart", icon: RotateCcw, color: "#9333ea", soft: "#f4eafd" },
};
