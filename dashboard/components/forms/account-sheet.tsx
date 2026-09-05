"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { accountFormSchema, type AccountFormValues } from "@/lib/account-schemas";
import { api, type BrandConfig, type RedditAccountItem } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

const NONE = "none";

const EMPTY_VALUES: AccountFormValues = {
  username: "",
  password: "",
  totp_secret: "",
  proxy_id: "",
  brand_id: "",
};

function apiErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // raw message
  }
  return error.message || fallback;
}

function selectValue(value: string | undefined) {
  return value && value.length > 0 ? value : NONE;
}

function fromSelectValue(value: string) {
  return value === NONE ? "" : value;
}

function optionalNumber(value: string | undefined) {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function enabledBrands(brands: BrandConfig[]) {
  return brands.filter((brand): brand is BrandConfig & { id: number } => {
    return brand.id != null && brand.is_enabled !== false;
  });
}

export function AccountSheet({
  open,
  onOpenChange,
  account = null,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account?: RedditAccountItem | null;
}) {
  const queryClient = useQueryClient();
  const isEdit = account != null;

  const form = useForm<AccountFormValues>({
    resolver: zodResolver(accountFormSchema),
    defaultValues: EMPTY_VALUES,
  });

  const proxiesQuery = useQuery({
    queryKey: queryKeys.proxies(),
    queryFn: () => api.proxies(),
    enabled: open,
    placeholderData: (previous) => previous,
  });
  const brandsQuery = useQuery({
    queryKey: queryKeys.brands(),
    queryFn: () => api.brands().catch(() => [] as BrandConfig[]),
    enabled: open,
    placeholderData: (previous) => previous,
  });

  const proxies = proxiesQuery.data ?? [];
  const brands = enabledBrands(brandsQuery.data ?? []);

  useEffect(() => {
    if (!open) return;
    form.reset({
      username: account?.username ?? "",
      password: "",
      totp_secret: "",
      proxy_id: account?.proxy_id != null ? String(account.proxy_id) : "",
      brand_id: account?.brand_id != null ? String(account.brand_id) : "",
    });
  }, [open, account, form]);

  const mutation = useMutation({
    mutationFn: async (values: AccountFormValues) => {
      const totp = values.totp_secret?.trim();
      const proxyId = optionalNumber(values.proxy_id);
      const brandId = optionalNumber(values.brand_id);
      if (isEdit && account) {
        return api.updateAccount(account.id, {
          ...(values.password?.trim() ? { password: values.password } : {}),
          ...(totp ? { totp_secret: totp } : {}),
          proxy_id: proxyId ?? 0,
          brand_id: brandId ?? 0,
        });
      }
      const password = values.password?.trim() ?? "";
      if (!password) {
        throw new Error("Password is required");
      }
      return api.createAccount({
        username: values.username.trim(),
        password,
        ...(totp ? { totp_secret: totp } : {}),
        ...(proxyId != null ? { proxy_id: proxyId } : {}),
        ...(brandId != null ? { brand_id: brandId } : {}),
      });
    },
    onSuccess: (saved) => {
      toast.success(isEdit ? `Updated ${saved.username}` : `Added ${saved.username}`);
      void queryClient.invalidateQueries({ queryKey: ["accounts-health"] });
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      toast.error(apiErrorMessage(error, isEdit ? "Failed to update account" : "Failed to add account"));
    },
  });

  function onSubmit(values: AccountFormValues) {
    if (!isEdit && !values.password?.trim()) {
      form.setError("password", { message: "Password is required" });
      return;
    }
    mutation.mutate(values);
  }

  const selectedProxyId = form.watch("proxy_id");
  const selectedProxy = proxies.find((proxy) => String(proxy.id) === selectedProxyId);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{isEdit ? "Edit account" : "Add account"}</SheetTitle>
          <SheetDescription>
            {isEdit
              ? "Update credentials, proxy, or brand for this Reddit account."
              : "Create a Reddit posting account. Password is required."}
          </SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 grid gap-4">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Username</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      autoComplete="username"
                      placeholder="redditbot01"
                      readOnly={isEdit}
                      className={isEdit ? "font-mono" : undefined}
                    />
                  </FormControl>
                  {isEdit ? (
                    <FormDescription>Username cannot be changed.</FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Password</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="password"
                      autoComplete={isEdit ? "new-password" : "current-password"}
                      placeholder={isEdit ? "Leave blank to keep" : undefined}
                    />
                  </FormControl>
                  {isEdit ? (
                    <FormDescription>Leave blank to keep the current password.</FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="totp_secret"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>TOTP secret</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder={
                        isEdit
                          ? "Leave blank to keep"
                          : "Optional. Paste the TOTP base32 secret."
                      }
                      className="min-h-16 font-mono text-xs"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="proxy_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Proxy</FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(fromSelectValue(value))}
                    value={selectValue(field.value)}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="None" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={NONE}>None</SelectItem>
                      {proxies.map((proxy) => (
                        <SelectItem key={proxy.id} value={String(proxy.id)}>
                          {proxy.label} — {proxy.host}:{proxy.port} — {proxy.account_count}{" "}
                          account{proxy.account_count === 1 ? "" : "s"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {selectedProxy && selectedProxy.account_count >= 1 ? (
                    <FormDescription>
                      This proxy already has {selectedProxy.account_count} account
                      {selectedProxy.account_count === 1 ? "" : "s"}. One account per proxy
                      is recommended.
                    </FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="brand_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Brand</FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(fromSelectValue(value))}
                    value={selectValue(field.value)}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Default / unbound" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={NONE}>Default / unbound</SelectItem>
                      {brands.map((brand) => (
                        <SelectItem key={brand.id} value={String(brand.id)}>
                          {brand.name}
                          {brand.is_active ? " (default)" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Bound accounts only post that product. Leave unbound for the default
                    brand.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SheetFooter className="mt-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending
                  ? isEdit
                    ? "Saving…"
                    : "Adding…"
                  : isEdit
                    ? "Save"
                    : "Add account"}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
