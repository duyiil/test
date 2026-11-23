import { useQuery } from "@tanstack/react-query";
import { currentUser } from "../api/resources";
import type { User } from "../api/types";

export function useCurrentUser(): User | undefined {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => (await currentUser()).data,
  });
  return query.data;
}
