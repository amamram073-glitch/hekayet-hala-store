import { describe, expect, it, vi } from "vitest";

const { getCatalogProducts } = vi.hoisted(() => ({
  getCatalogProducts: vi.fn(),
}));

vi.mock("./db", () => ({ getCatalogProducts }));

import { appRouter } from "./routers";
import type { TrpcContext } from "./_core/context";

const context: TrpcContext = {
  user: null,
  req: {} as TrpcContext["req"],
  res: {} as TrpcContext["res"],
};

describe("catalog.list", () => {
  it("returns persisted active catalog products to public visitors", async () => {
    const databaseProducts = [
      {
        id: 15,
        slug: "premium-cake",
        name: "كيك فاخر",
        price: 100,
        image: "/manus-storage/premium-cake_2bd487df.webp",
        description: "كيك فاخر بطبقات كريمة ومزين بالفواكه.",
        tag: "عائلي",
        collection: "family",
        isActive: true,
        createdAt: new Date("2026-09-27T00:00:00.000Z"),
        updatedAt: new Date("2026-09-27T00:00:00.000Z"),
      },
    ];
    getCatalogProducts.mockResolvedValueOnce(databaseProducts);

    const caller = appRouter.createCaller(context);
    await expect(caller.catalog.list()).resolves.toEqual(databaseProducts);
    expect(getCatalogProducts).toHaveBeenCalledOnce();
  });
});
