"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { cookiesSchema, type CookiesFormValues } from "@/lib/account-schemas";
import { api, type RedditAccountItem } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

function uploadErrorMessage(result: {
  ok: boolean;
  status: number;
  errorText: string;
}) {
  try {
    const body = JSON.parse(result.errorText) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // raw text
  }
  return result.errorText || `HTTP ${result.status}`;
}

export function CookiesSheet({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: RedditAccountItem | null;
}) {
  const queryClient = useQueryClient();
  const form = useForm<CookiesFormValues>({
    resolver: zodResolver(cookiesSchema),
    defaultValues: { raw: "" },
  });

  useEffect(() => {
    if (!open) return;
    form.reset({ raw: "" });
  }, [open, account, form]);

  const mutation = useMutation({
    mutationFn: async (values: CookiesFormValues) => {
      if (!account) throw new Error("No account selected");
      const result = await api.uploadCookies(account.id, values.raw);
      if (!result.ok) {
        throw new Error(uploadErrorMessage(result));
      }
      return result.data as RedditAccountItem;
    },
    onSuccess: (saved) => {
      toast.success(`Cookies saved for ${saved.username ?? account?.username}`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountsHealth(true) });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to save cookies");
    },
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            Paste cookies{account ? ` — u/${account.username}` : ""}
          </SheetTitle>
          <SheetDescription>
            Paste a <code>reddit_session</code> value, a <code>name=value</code> cookie
            header, or a Cookie-Editor JSON export. Log in through this account&apos;s
            proxy when possible so the session IP matches the worker.
          </SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            className="mt-6 grid gap-4"
          >
            <FormField
              control={form.control}
              name="raw"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Cookie payload</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      className="min-h-[140px] font-mono text-xs"
                      placeholder='reddit_session value, OR "name=value; name=value", OR Cookie-Editor JSON array'
                      disabled={mutation.isPending || !account}
                    />
                  </FormControl>
                  <FormDescription>
                    {account?.has_cookies
                      ? `Cookies already stored${
                          account.cookies_set_at
                            ? ` ${new Date(account.cookies_set_at).toLocaleString()}`
                            : ""
                        }.`
                      : "No cookies stored yet."}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SheetFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending || !account}>
                {mutation.isPending ? "Saving…" : "Save cookies"}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
