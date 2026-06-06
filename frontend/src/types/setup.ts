export interface SetupOptionResponse {
  id: number;
  name: string;
  is_active: boolean;
  sort_order: number | null;
}

export interface CreateSetupOptionRequest {
  name: string;
  is_active?: boolean;
  sort_order?: number | null;
}

export interface UpdateSetupOptionRequest {
  name?: string;
  is_active?: boolean;
  sort_order?: number | null;
}
