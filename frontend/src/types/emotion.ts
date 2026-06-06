export interface EmotionOptionResponse {
  id: number;
  name: string;
  is_active: boolean;
  sort_order: number | null;
}

export interface CreateEmotionOptionRequest {
  name: string;
  is_active?: boolean;
  sort_order?: number | null;
}

export interface UpdateEmotionOptionRequest {
  name?: string;
  is_active?: boolean;
  sort_order?: number | null;
}
