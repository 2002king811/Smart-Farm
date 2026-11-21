import type { LucideIcon } from 'lucide-react';
import {
  Baby,
  Bell,
  CalendarDays,
  ClipboardList,
  FileBarChart,
  HeartPulse,
  Home,
  LayoutDashboard,
  ListChecks,
  PawPrint,
  Settings,
  Users,
  Wheat,
} from 'lucide-react';

import type { Module } from './permissions';

export interface NavItem {
  path: string;
  /** i18n key under "nav." */
  key: string;
  module: Module;
  icon: LucideIcon;
  /** Build phase that delivers the screen (see README). */
  phase: number;
}

/** Desktop sidebar, in prototype order. */
export const SIDEBAR_ITEMS: NavItem[] = [
  { path: '/dashboard', key: 'dashboard', module: 'dashboard', icon: LayoutDashboard, phase: 7 },
  { path: '/livestock', key: 'livestock', module: 'livestock', icon: PawPrint, phase: 3 },
  { path: '/health', key: 'health', module: 'health', icon: HeartPulse, phase: 4 },
  { path: '/calendar', key: 'calendar', module: 'calendar', icon: CalendarDays, phase: 4 },
  { path: '/activities', key: 'activities', module: 'activities', icon: ClipboardList, phase: 4 },
  { path: '/breeding', key: 'breeding', module: 'breeding', icon: Baby, phase: 5 },
  { path: '/nutrition', key: 'nutrition', module: 'nutrition', icon: Wheat, phase: 5 },
  { path: '/notifications', key: 'notifications', module: 'notifications', icon: Bell, phase: 6 },
  { path: '/reports', key: 'reports', module: 'reports', icon: FileBarChart, phase: 7 },
  { path: '/users', key: 'users', module: 'users', icon: Users, phase: 2 },
  { path: '/settings', key: 'settings', module: 'settings', icon: Settings, phase: 2 },
];

/** Attendant phone view: bottom navigation (Home, Tasks, Animals, Calendar, Alerts). */
export const MOBILE_ITEMS: NavItem[] = [
  { path: '/dashboard', key: 'home', module: 'dashboard', icon: Home, phase: 7 },
  { path: '/activities', key: 'tasks', module: 'activities', icon: ListChecks, phase: 4 },
  { path: '/livestock', key: 'animals', module: 'livestock', icon: PawPrint, phase: 3 },
  { path: '/calendar', key: 'calendarShort', module: 'calendar', icon: CalendarDays, phase: 4 },
  { path: '/notifications', key: 'alerts', module: 'notifications', icon: Bell, phase: 6 },
];
