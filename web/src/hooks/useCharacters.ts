import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { charactersApi } from "@/api/characters";

export function useCharacters(bookId: string | undefined) {
  return useQuery({
    queryKey: ["characters", bookId],
    queryFn: () => charactersApi.list(bookId ?? ""),
    enabled: Boolean(bookId)
  });
}

export function useCharacterRelationships(bookId: string | undefined) {
  return useQuery({
    queryKey: ["character-relationships", bookId],
    queryFn: () => charactersApi.relationships(bookId ?? ""),
    enabled: Boolean(bookId)
  });
}

export function useCreateCharacter(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (spec: string) => charactersApi.create(bookId, spec),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["characters", bookId] })
  });
}
