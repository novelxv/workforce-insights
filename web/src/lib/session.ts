"use client";

import useSWR from "swr";

import { fetcher } from "./api";
import type { Me, Meta } from "./types";

export function useMe() {
  const { data, error, isLoading } = useSWR<Me>("/auth/me", fetcher, { revalidateOnFocus: false });
  return { me: data, error, isLoading };
}

/** The semantic layer as this user may use it. Changes only when the warehouse is rebuilt. */
export function useMeta() {
  const { data, error } = useSWR<Meta>("/meta", fetcher, { revalidateOnFocus: false });
  return { meta: data, error };
}
