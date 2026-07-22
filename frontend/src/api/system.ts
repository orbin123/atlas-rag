import { apiRequest } from './client';
import type { SystemInfo } from '../types';
export const getSystemInfo = () => apiRequest<SystemInfo>('/system/info');
