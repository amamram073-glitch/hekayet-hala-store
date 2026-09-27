import { describe, expect, it } from "vitest";
import { catalogSeed } from "../shared/catalog";
import { getCyclicSlideIndex } from "../client/src/lib/familySlider";

const familyProducts = catalogSeed.filter((product) => product.collection === "family");

describe("family-product login slider", () => {
  it("has an image for each of the six family products shown at AED 100", () => {
    expect(familyProducts).toHaveLength(6);
    expect(familyProducts.every((product) => product.image.startsWith("/manus-storage/"))).toBe(true);
    expect(familyProducts.map((product) => product.price)).toEqual([100, 100, 100, 100, 100, 100]);
  });

  it("wraps next and previous controls across the ends of the slider", () => {
    expect(getCyclicSlideIndex(5, 1, familyProducts.length)).toBe(0);
    expect(getCyclicSlideIndex(0, -1, familyProducts.length)).toBe(5);
  });

  it("safely handles an empty slide list", () => {
    expect(getCyclicSlideIndex(0, 1, 0)).toBe(0);
  });
});
