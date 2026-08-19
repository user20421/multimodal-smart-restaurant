/**
 * 认证相关 API
 */
import api from '@/shared/api/client'
import type { AuthResponse, User } from '@/shared/types'

export interface LoginPayload {
  username: string
  password: string
  captcha_id: string
  captcha_code: string
}

export interface CaptchaResponse {
  captcha_id: string
  image_base64: string
}

export interface RegisterPayload {
  username: string
  password: string
  phone?: string
  gender?: 'unknown' | 'male' | 'female'
  birth_date?: string
  role?: 'customer' | 'admin'
}

export interface ProfileUpdatePayload {
  phone?: string
  gender?: 'unknown' | 'male' | 'female'
  birth_date?: string
}

export interface ChangePasswordPayload {
  old_password?: string  // 首次强制改密场景可不传
  new_password: string
}

export interface FaceLoginPayload {
  face_image_base64: string
}

export interface FaceRegisterPayload {
  face_image_base64: string
}

export function login(payload: LoginPayload) {
  return api.post<AuthResponse>('/auth/login', payload)
}

export function register(payload: RegisterPayload) {
  return api.post<AuthResponse>('/auth/register', payload)
}

export function changePassword(payload: ChangePasswordPayload) {
  return api.post<User>('/auth/change-password', payload)
}

export function getProfile() {
  return api.get<User>('/auth/profile')
}

export function updateProfile(payload: ProfileUpdatePayload) {
  return api.put<User>('/auth/profile', payload)
}

export function getCaptcha() {
  return api.get<CaptchaResponse>('/auth/captcha')
}

export function faceLogin(payload: FaceLoginPayload) {
  return api.post<AuthResponse>('/auth/face-login', payload)
}

export function registerFace(payload: FaceRegisterPayload) {
  return api.post<User>('/auth/face-register', payload)
}
