import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { booksApi, type CreateBookRequest } from "@/api/books";

export function useBooks() {
  return useQuery({
    queryKey: ["books"],
    queryFn: booksApi.list
  });
}

export function useBook(id: string | undefined) {
  return useQuery({
    queryKey: ["book", id],
    queryFn: () => booksApi.get(id ?? ""),
    enabled: Boolean(id)
  });
}

export function useCreateBook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateBookRequest) => booksApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["books"] })
  });
}
