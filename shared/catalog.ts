export type CatalogCollection = "classic" | "family";

export interface CatalogSeedProduct {
  slug: string;
  name: string;
  price: number;
  image: string;
  description: string;
  tag: string;
  collection: CatalogCollection;
}

export const catalogSeed: CatalogSeedProduct[] = [
  { slug: "cheesecake-cup", name: "تشيز كيك", price: 18, image: "/manus-storage/cheesecake_558e507c.jpeg", description: "تشيز كيك كريمي بطبقة فستق حلبي فلسطيني، وصفة جداتنا الأصيلة.", tag: "بارد", collection: "classic" },
  { slug: "layali-lebanon", name: "ليالي لبنان", price: 18, image: "/manus-storage/layali-lebanon_ca243630.jpeg", description: "حلى ليالي لبنان الناعم بسميد وحليب، مزيّن بالفستق وماء الزهر.", tag: "تراثي", collection: "classic" },
  { slug: "palestinian-halba", name: "الحلبة الفلسطينية", price: 17, image: "/manus-storage/halba_b11748a8.jpeg", description: "حلبة بزيت زيتون بكر، بنكهة حلبة وسمسم محمّص.", tag: "تراثي", collection: "classic" },
  { slug: "palestinian-cinnamon-roll", name: "سينابون الفلسطيني", price: 19, image: "/manus-storage/sinabon2_167424f4.jpeg", description: "لفائف قرفة هشة بصوص كريمي فاخر.", tag: "مخبوز", collection: "classic" },
  { slug: "date-kaak", name: "كعك أساور بالتمر الفاخر", price: 16, image: "/manus-storage/kaak-asawer_68d26c1d.jpeg", description: "كعك أساور نابلسي محشو تمر ملوكي وسمسم بلدي.", tag: "تمر", collection: "classic" },
  { slug: "date-maamoul", name: "معمول بالتمر الفاخر", price: 16, image: "/manus-storage/maamoul_afd864a4.jpeg", description: "معمول هش يذوب بالفم، محشو تمر معطر بالهيل.", tag: "تمر", collection: "classic" },
  { slug: "petit-four", name: "بيتفور", price: 17, image: "/manus-storage/petitfour_35f57354.jpeg", description: "بيتفور زبدة فاخر بمربى مشمش طبيعي.", tag: "مخبوز", collection: "classic" },
  { slug: "maqroute", name: "مقروطة", price: 17, image: "/manus-storage/maqrouta_061f8551.jpeg", description: "مقروطة محمّصة بالسمن البلدي وتمر مجدول.", tag: "تمر", collection: "classic" },
  { slug: "mabshoura", name: "مبشورة", price: 16, image: "/manus-storage/mabshoura_04f58b59.jpeg", description: "مبشورة هشة بطبقات تفاح وقرفة.", tag: "مخبوز", collection: "classic" },
  { slug: "family-box", name: "بوكس العائلة", price: 100, image: "/manus-storage/family-box_a8f9c1f4.webp", description: "تشكيلة عائلية من حلويات حكاية حلا الفلسطينية.", tag: "عائلي", collection: "family" },
  { slug: "gift-box", name: "بوكس إهداء من القلب", price: 100, image: "/manus-storage/gift-box_8e41bbed.webp", description: "تشكيلة حلويات أنيقة مناسبة للإهداء والمناسبات.", tag: "عائلي", collection: "family" },
  { slug: "cheesecake-box", name: "بوكس تشيز كيك", price: 100, image: "/manus-storage/cheesecake-box_2a61d9d0.webp", description: "قطع تشيز كيك مزينة بالفراولة والشوكولاتة.", tag: "عائلي", collection: "family" },
  { slug: "dessert-pizza", name: "بيتزا حكاية حلا", price: 100, image: "/manus-storage/dessert-pizza_b0e54ce9.webp", description: "بيتزا حلوة بثلاث نكهات ظاهرة في الصورة: الشوكولاتة والفراولة والفستق.", tag: "عائلي", collection: "family" },
  { slug: "cheesecake-duo", name: "بوكس تشيز كيك بالفراولة والشوكولاتة", price: 100, image: "/manus-storage/cheesecake-duo_ec25fe70.webp", description: "بوكس يضم تشيز كيك بالفراولة وتشيز كيك بالشوكولاتة.", tag: "عائلي", collection: "family" },
  { slug: "premium-cake", name: "كيك فاخر", price: 100, image: "/manus-storage/premium-cake_2bd487df.webp", description: "كيك فاخر بطبقات كريمة ومزين بالفواكه.", tag: "عائلي", collection: "family" },
];
