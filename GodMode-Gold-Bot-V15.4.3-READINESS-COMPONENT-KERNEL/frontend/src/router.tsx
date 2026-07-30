import { lazy, type ComponentType } from 'react';

const Dashboard=lazy(()=>import('./pages/Dashboard'));
const Signals=lazy(()=>import('./pages/Signals'));
const Strategies=lazy(()=>import('./pages/Strategies'));
const Trades=lazy(()=>import('./pages/Trades'));
const Risk=lazy(()=>import('./pages/Risk'));
const AIAgent=lazy(()=>import('./pages/AIAgent'));
const Analytics=lazy(()=>import('./pages/Analytics'));
const Journal=lazy(()=>import('./pages/Journal'));
const Settings=lazy(()=>import('./pages/Settings'));
const Health=lazy(()=>import('./pages/Health'));
const Login=lazy(()=>import('./pages/Login'));

export const pages: Record<string, ComponentType>={dashboard:Dashboard,signals:Signals,strategies:Strategies,trades:Trades,ai:AIAgent,risk:Risk,analytics:Analytics,journal:Journal,settings:Settings,health:Health,login:Login};
