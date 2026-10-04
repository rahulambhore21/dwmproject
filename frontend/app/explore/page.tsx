"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { PageHeader } from "@/components/editorial";
import { LoadingBlock } from "@/components/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTab } from "./data-tab";
import { DriversTab } from "./drivers-tab";
import { PivotTab } from "./pivot-tab";
import { SegmentsTab } from "./segments-tab";

const TABS = ["pivot", "drivers", "segments", "models"] as const;

export default function ExplorePage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} label="Loading explorer" />}>
      <Explorer />
    </Suspense>
  );
}

function Explorer() {
  const sp = useSearchParams();
  const router = useRouter();
  const raw = sp.get("tab");
  const tab = (TABS as readonly string[]).includes(raw ?? "") ? (raw as string) : raw === "data" ? "models" : "pivot";
  return (
    <>
      <PageHeader eyebrow="06 · Analyse" title="Ask the warehouse." lede="Slice the star schema yourself, see which attributes carry signal and which are noise, and inspect every stored model run: parameters, metrics and what they can't tell you." />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/explore?tab=${v}`, { scroll: false })}>
        <TabsList aria-label="Explorer sections">
          <TabsTrigger value="pivot">OLAP pivot</TabsTrigger>
          <TabsTrigger value="drivers">Drivers</TabsTrigger>
          <TabsTrigger value="segments">Segments</TabsTrigger>
          <TabsTrigger value="models">Models & data</TabsTrigger>
        </TabsList>
        <div className="pt-8">
          <TabsContent value="pivot"><PivotTab /></TabsContent>
          <TabsContent value="drivers"><DriversTab /></TabsContent>
          <TabsContent value="segments"><SegmentsTab /></TabsContent>
          <TabsContent value="models"><DataTab /></TabsContent>
        </div>
      </Tabs>
    </>
  );
}
