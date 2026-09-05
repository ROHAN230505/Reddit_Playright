import { z } from "zod";

export const accountFormSchema = z.object({
  username: z.string().min(1).max(255),
  password: z.string().optional(),
  totp_secret: z.string().optional(),
  proxy_id: z.string().optional(),
  brand_id: z.string().optional(),
});

export const cookiesSchema = z.object({
  raw: z.string().min(1, "Paste a cookie value first."),
});

export type AccountFormValues = z.infer<typeof accountFormSchema>;
export type CookiesFormValues = z.infer<typeof cookiesSchema>;
