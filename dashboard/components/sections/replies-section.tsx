"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { RecentlyPostedPanel } from "@/components/recently-posted";
import { PostedAnalytics } from "@/components/posted-analytics";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type ReplySummary } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 30;
const EMPTY_ROWS: ReplySummary[] = [];

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

const columnHelper = createColumnHelper<typeof features, ReplySummary>();

export default function RepliesSection() {
  const postedQuery = useQuery({
    queryKey: queryKeys.repliesSummary("POSTED", "reddit"),
    queryFn: () => api.repliesSummary("POSTED", 800, "reddit"),
    refetchInterval: visibleRefetchInterval(30_000),
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });
  const failedQuery = useQuery({
    queryKey: queryKeys.repliesSummary("FAILED", "reddit"),
    queryFn: () => api.repliesSummary("FAILED", 400, "reddit"),
    refetchInterval: visibleRefetchInterval(30_000),
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });

  const posted = postedQuery.data;
  const failed = failedQuery.data ?? EMPTY_ROWS;
  const error =
    postedQuery.error instanceof Error
      ? postedQuery.error.message
      : postedQuery.isError
        ? "Could not load Reddit posted replies."
        : "";

  if (postedQuery.isPending && !posted) {
    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Posted replies</h2>
          <p className="text-sm text-muted-foreground">Reddit posts placed, with 14-day volume and recent links.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-48" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  const rows = posted ?? EMPTY_ROWS;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Posted replies</h2>
        <p className="text-sm text-muted-foreground">Reddit posts placed, with 14-day volume and recent links.</p>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Could not load Reddit replies</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-2">
            <span>{error}</span>
            <Button type="button" size="sm" variant="outline" onClick={() => void postedQuery.refetch()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {!error && rows.length === 0 && (
        <Alert>
          <AlertTitle>No posted Reddit replies yet</AlertTitle>
          <AlertDescription>Posted replies will appear here after successful posting.</AlertDescription>
        </Alert>
      )}
      <PostedAnalytics posted={rows} groupLabel="Top subreddits" groupMode="subreddit" barClass="bg-orange-400" />
      <PostedFailedTable posted={rows} failed={failed} />
      <RecentlyPostedPanel posted={rows} subtitle="Reddit · newest first" />
    </div>
  );
}

function PostedFailedTable({
  posted,
  failed,
}: {
  posted: ReplySummary[];
  failed: ReplySummary[];
}) {
  const [statusFilter, setStatusFilter] = useState<"ALL" | "POSTED" | "FAILED">("ALL");
  const [subredditFilter, setSubredditFilter] = useState("");

  const tableData = useMemo(() => {
    const rows = [
      ...(statusFilter !== "FAILED" ? posted : EMPTY_ROWS),
      ...(statusFilter !== "POSTED" ? failed : EMPTY_ROWS),
    ];
    const needle = subredditFilter.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => (row.subreddit || "").toLowerCase().includes(needle));
  }, [failed, posted, statusFilter, subredditFilter]);

  const columns = useMemo(
    () =>
      columnHelper.columns([
        columnHelper.accessor("status", {
          header: "Status",
          cell: ({ getValue }) => {
            const status = getValue();
            return (
              <Badge variant={status === "FAILED" ? "destructive" : "secondary"}>
                {status}
              </Badge>
            );
          },
        }),
        columnHelper.accessor("subreddit", {
          header: "Subreddit",
          cell: ({ getValue }) => {
            const name = getValue();
            return <span className="font-mono text-xs">{name ? `r/${name}` : "n/a"}</span>;
          },
        }),
        columnHelper.accessor((row) => row.posted_at || row.created_at, {
          id: "when",
          header: "Date",
          cell: ({ getValue }) => (
            <span className="font-mono text-xs text-muted-foreground">{formatDate(getValue())}</span>
          ),
        }),
        columnHelper.accessor("reply_text", {
          header: "Reply",
          cell: ({ getValue }) => (
            <span className="line-clamp-2 max-w-md text-sm text-foreground" title={getValue()}>
              {getValue()}
            </span>
          ),
        }),
        columnHelper.display({
          id: "link",
          header: "Link",
          cell: ({ row }) => {
            const url = row.original.posted_url?.trim();
            if (!url) {
              return <span className="text-xs italic text-muted-foreground">link not available</span>;
            }
            return (
              <a
                href={url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs text-primary hover:underline"
              >
                View
              </a>
            );
          },
        }),
      ]),
    [],
  );

  const table = useTable({
    features,
    columns,
    data: tableData.length > 0 ? tableData : EMPTY_ROWS,
    getRowId: (row) => `${row.status}-${row.reply_id}`,
    autoResetPageIndex: true,
    initialState: {
      pagination: { pageIndex: 0, pageSize: PAGE_SIZE },
    },
  });

  const rows = table.getRowModel().rows;
  const pageIndex = table.state.pagination.pageIndex;
  const pageSize = table.state.pagination.pageSize;
  const rowCount = table.getRowCount();
  const from = rowCount === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(rowCount, (pageIndex + 1) * pageSize);

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Posted / failed</h2>
          <p className="text-xs text-muted-foreground">Filter by status and subreddit. 30 per page.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as "ALL" | "POSTED" | "FAILED")}
          >
            <SelectTrigger className="h-8 w-36" aria-label="Filter by status">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All statuses</SelectItem>
              <SelectItem value="POSTED">Posted</SelectItem>
              <SelectItem value="FAILED">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Input
            value={subredditFilter}
            onChange={(event) => setSubredditFilter(event.target.value)}
            placeholder="Filter subreddit…"
            className="h-8 w-full max-w-xs"
            aria-label="Filter by subreddit"
          />
        </div>
      </div>
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={table.getAllColumns().length} className="h-24 text-center text-muted-foreground">
                No replies match these filters.
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={row.id}>
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>{rowCount === 0 ? "0 replies" : `${from}–${to} of ${rowCount}`}</span>
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
    </Card>
  );
}
