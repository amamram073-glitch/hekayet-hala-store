import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL ?? "https://nkagrazdklltmqpoysgm.supabase.co";
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "sb_publishable_ORYFfVD5VYAQ6vebN6zx0A_pCXQ-r3b";

export const isSupabaseConfigured = Boolean(url && publishableKey);
export const supabase: SupabaseClient = createClient(url, publishableKey, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});

export type SupabaseUser = User;
export const supabaseUrl = url;
export const productImageBucket = "product-images";
