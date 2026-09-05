"use client";

import { useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  columnFilteringFeature,
  filterFn_includesString,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import { AccountSheet } from "@/components/forms/account-sheet";
import { CookiesSheet } from "@/components/forms/cookies-sheet";
import { HealthBadge } from "@/components/reddit/health-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type AccountActivity, type RedditAccountItem } from "@/lib/api";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";
import { queryKeys } from "@/lib/query-keys";
import { cn, formatDate } from "@/lib/utils";

type AccountRow = RedditAccountItem & {
  posts_last_hour: number;
  hourly_limit: number;
};

const EMPTY_DATA: AccountRow[] = [];
const PAGE_SIZE = 25;
const VIRTUALIZE_AFTER = 50;

const features = tableFeatures({
  columnFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});

const columnHelper = createColumnHelper<typeof features, AccountRow>();

function relativeTime(value: string | null) {
  if (!value) return "n/a";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;
  const diff = Math.floor((Date.now() - then) / 1000);
  if (diff < 60) return `${Math.max(0, diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function activityFor(
  activity: Record<number, AccountActivity> | undefined,
  id: number,
) {
  if (!activity) return undefined;
  return activity[id] ?? (activity as Record<string, AccountActivity | undefined>)[String(id)];
}

function SortHeader({
  column,
  children,
}: {
  column: {
    getCanSort: () => boolean;
    getIsSorted: () => false | "asc" | "desc";
    getToggleSortingHandler: () => undefined | ((event: unknown) => void);
  };
  children: ReactNode;
}) {
  const sorted = column.getIsSorted();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="-ml-3 h-8"
      disabled={!column.getCanSort()}
      onClick={column.getToggleSortingHandler()}
    >
      {children}
      {sorted === "asc" ? (
        <ArrowUp />
      ) : sorted === "desc" ? (
        <ArrowDown />
      ) : (
        <ArrowUpDown className="opacity-40" />
      )}
    </Button>
  );
}

function AccountActions({
  account,
  onEdit,
  onCookies,
}: {
  account: RedditAccountItem;
  onEdit: (account: RedditAccountItem) => void;
  onCookies: (account: RedditAccountItem) => void;
}) {
  const queryClient = useQueryClient();
  const toggleEnabled = useMutation({
    mutationFn: () => api.updateAccount(account.id, { is_enabled: !account.is_enabled }),
    onSuccess: (updated) => {
      toast.success(
        updated.is_enabled ? `Enabled ${updated.username}` : `Disabled ${updated.username}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["accounts-health"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to update account");
    },
  });
  const reverify = useMutation({
    mutationFn: () => api.reverifyAccount(account.id),
    onSuccess: () => {
      toast.success(`Reverify started for ${account.username}`);
      void queryClient.invalidateQueries({ queryKey: ["accounts-health"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Reverify failed");
    },
  });
  const busy = toggleEnabled.isPending || reverify.isPending;

  return (
    <div className="inline-flex flex-nowrap items-center justify-end gap-1">
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-8 w-14 justify-center px-0"
        onClick={() => onEdit(account)}
      >
        Edit
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-8 w-[4.75rem] justify-center px-0"
        onClick={() => onCookies(account)}
      >
        {account.has_cookies ? "Cookies ✓" : "Cookies"}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-8 w-16 justify-center px-0"
        disabled={busy}
        onClick={() => toggleEnabled.mutate()}
      >
        {account.is_enabled ? "Disable" : "Enable"}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-8 w-[4.5rem] justify-center px-0"
        disabled={busy}
        onClick={() => reverify.mutate()}
      >
        Reverify
      </Button>
    </div>
  );
}

function ErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Could not load accounts</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-2">
        <span>The live health fetch failed. Previous data stays if it is available.</span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function AccountTable() {
  const { data, isPending, isError, refetch } = useAccountsHealth(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editAccount, setEditAccount] = useState<RedditAccountItem | null>(null);
  const [cookiesAccount, setCookiesAccount] = useState<RedditAccountItem | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const tableData = useMemo(() => {
    const accounts = (data?.accounts ?? []).filter(
      (account) => (account.platform || "reddit") === "reddit",
    );
    return accounts.map((account) => {
      const activity = activityFor(data?.activity, account.id);
      return {
        ...account,
        posts_last_hour: activity?.posts_last_hour ?? 0,
        hourly_limit:
          activity?.posts_per_hour_limit ?? account.posts_per_hour_limit ?? 0,
      };
    });
  }, [data]);

  const columns = useMemo(
    () =>
      columnHelper.columns([
        columnHelper.accessor("username", {
          header: ({ column }) => <SortHeader column={column}>Username</SortHeader>,
          cell: ({ getValue }) => (
            <span className="font-mono text-sm font-medium">{getValue()}</span>
          ),
          filterFn: "includesString",
        }),
        columnHelper.accessor("reddit_health", {
          id: "health",
          header: ({ column }) => <SortHeader column={column}>Health</SortHeader>,
          cell: ({ row }) => <HealthBadge account={row.original} />,
        }),
        columnHelper.accessor("posts_last_hour", {
          id: "usage",
          header: ({ column }) => <SortHeader column={column}>Usage</SortHeader>,
          cell: ({ row }) => (
            <span className="font-mono text-sm tabular-nums">
              {row.original.posts_last_hour}/{row.original.hourly_limit}
            </span>
          ),
        }),
        columnHelper.accessor("proxy_label", {
          header: ({ column }) => <SortHeader column={column}>Proxy</SortHeader>,
          cell: ({ getValue }) => (
            <span className="text-sm text-muted-foreground">{getValue() ?? "—"}</span>
          ),
        }),
        columnHelper.accessor("last_seen_at", {
          header: ({ column }) => <SortHeader column={column}>Last seen</SortHeader>,
          cell: ({ getValue }) => {
            const value = getValue();
            return (
              <span className="font-mono text-xs text-muted-foreground" title={formatDate(value)}>
                {relativeTime(value)}
              </span>
            );
          },
          sortUndefined: "last",
        }),
        columnHelper.display({
          id: "actions",
          header: () => <span className="sr-only">Actions</span>,
          enableSorting: false,
          cell: ({ row }) => (
            <AccountActions
              account={row.original}
              onEdit={setEditAccount}
              onCookies={setCookiesAccount}
            />
          ),
        }),
      ]),
    [],
  );

  const table = useTable({
    features,
    columns,
    data: tableData.length > 0 ? tableData : EMPTY_DATA,
    getRowId: (row) => String(row.id),
    autoResetPageIndex: false,
    initialState: {
      pagination: { pageIndex: 0, pageSize: PAGE_SIZE },
    },
  });

  const rows = table.getRowModel().rows;
  const virtualize = rows.length > VIRTUALIZE_AFTER;
  const virtualizer = useVirtualizer({
    count: virtualize ? rows.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 56,
    overscan: 8,
    getItemKey: (index) => rows[index]?.id ?? index,
  });
  const virtualItems = virtualize ? virtualizer.getVirtualItems() : null;
  const paddingTop =
    virtualItems && virtualItems.length > 0 ? (virtualItems[0]?.start ?? 0) : 0;
  const paddingBottom =
    virtualItems && virtualItems.length > 0
      ? virtualizer.getTotalSize() - (virtualItems[virtualItems.length - 1]?.end ?? 0)
      : 0;
  const colSpan = table.getAllColumns().length;
  const pageIndex = table.state.pagination.pageIndex;
  const pageSize = table.state.pagination.pageSize;
  const rowCount = table.getRowCount();
  const from = rowCount === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(rowCount, (pageIndex + 1) * pageSize);
  const usernameFilter = (table.getColumn("username")?.getFilterValue() as string) ?? "";

  if (isPending && !data) {
    return <Skeleton className="h-64 w-full rounded-xl" />;
  }

  const renderedRows = virtualItems
    ? virtualItems.map((item) => ({ item, row: rows[item.index] }))
    : rows.map((row, index) => ({ item: { index }, row }));

  return (
    <div className="space-y-4">
      {isError ? <ErrorBanner onRetry={() => void refetch()} /> : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          value={usernameFilter}
          onChange={(event) => {
            table.getColumn("username")?.setFilterValue(event.target.value);
            table.setPageIndex(0);
          }}
          placeholder="Filter username…"
          className="h-8 w-full max-w-xs"
          aria-label="Filter by username"
        />
        <Button
          type="button"
          size="sm"
          onClick={() => {
            setEditAccount(null);
            setCreateOpen(true);
          }}
        >
          <Plus />
          Add account
        </Button>
      </div>
      <div
        ref={scrollRef}
        className={cn(virtualize && "max-h-[min(70vh,720px)] overflow-auto")}
      >
        <Table>
          <TableHeader className={virtualize ? "sticky top-0 z-10 bg-background" : undefined}>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className={header.id === "actions" ? "w-[1%] whitespace-nowrap text-right" : undefined}
                  >
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {paddingTop > 0 ? (
              <tr>
                <td colSpan={colSpan} style={{ height: paddingTop }} />
              </tr>
            ) : null}
            {renderedRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={colSpan} className="h-24 text-center text-muted-foreground">
                  {tableData.length === 0
                    ? "No Reddit accounts."
                    : "No usernames match this filter."}
                </TableCell>
              </TableRow>
            ) : (
              renderedRows.map(({ item, row }) => {
                if (!row) return null;
                return (
                  <TableRow
                    key={row.id}
                    data-index={virtualize ? item.index : undefined}
                    ref={virtualize ? virtualizer.measureElement : undefined}
                  >
                    {row.getAllCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={
                          cell.column.id === "actions" ? "w-[1%] whitespace-nowrap text-right" : undefined
                        }
                      >
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })
            )}
            {paddingBottom > 0 ? (
              <tr>
                <td colSpan={colSpan} style={{ height: paddingBottom }} />
              </tr>
            ) : null}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>
          {rowCount === 0 ? "0 accounts" : `${from}–${to} of ${rowCount}`}
        </span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft />
            Previous
          </Button>
          <span className="tabular-nums">
            Page {pageIndex + 1} of {Math.max(1, table.getPageCount())}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            Next
            <ChevronRight />
          </Button>
        </div>
      </div>
      <AccountSheet
        open={createOpen || editAccount != null}
        onOpenChange={(open) => {
          if (!open) {
            setCreateOpen(false);
            setEditAccount(null);
          }
        }}
        account={editAccount}
      />
      <CookiesSheet
        open={cookiesAccount != null}
        onOpenChange={(open) => {
          if (!open) setCookiesAccount(null);
        }}
        account={cookiesAccount}
      />
    </div>
  );
}
