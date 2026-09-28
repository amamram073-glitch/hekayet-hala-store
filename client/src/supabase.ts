import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";

// GitHub Actions exposes an unset secret as an empty string. Use the public
// project defaults in that case so a missing optional secret cannot blank the
// storefront at runtime. The publishable key is safe to ship in a browser;
// never place a Supabase secret/service-role key here.
const url = import.meta.env.VITE_SUPABASE_URL || "https://nkagrazdklltmqpoysgm.supabase.co";
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || "sb_publishable_ORYFfVD5VYAQ6vebN6zx0A_pCXQ-r3b";

export const isSupabaseConfigured = Boolean(url && publishableKey);
export const supabase: SupabaseClient = createClient(url, publishableKey, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});

export type SupabaseUser = User;
export const supabaseUrl = url;
export const productImageBucket = "product-images";
