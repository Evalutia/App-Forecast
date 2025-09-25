import { useMutation, useQueryClient } from '@tanstack/react-query';
import { login } from '../../../api/auth';
import type { LoginRequest, LoginResponse } from '../types/auth';
import { saveAuth } from '../utils/authStorage';

export function useLogin() {
  const qc = useQueryClient();
  return useMutation<LoginResponse, any, LoginRequest>({
    mutationFn: (payload) => login(payload),
    onSuccess: (data) => {
      saveAuth(data.token, data.user);
      qc.invalidateQueries({ queryKey: ['auth'] });
    },
  });
}
