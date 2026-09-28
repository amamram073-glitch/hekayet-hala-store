-- بيانات منتجات حكاية حلا في Supabase
insert into public.products (id, slug, name, price, image, description, tag, collection, stock, active) values
(1, 'cheesecake-cup', 'حكاية حلا', 18, '/manus-storage/cheesecake_558e507c.jpeg', 'تشيز كيك كريمي بطبقة فستق حلبي فلسطيني، وصفة جداتنا الأصيلة.', 'بارد', 'classic', 20, true),
(2, 'layali-lebanon', 'تشيز كيك', 18, '/manus-storage/layali-lebanon_ca243630.jpeg', 'حلى ليالي لبنان الناعم بسميد وحليب، مزيّن بالفستق وماء الزهر.', 'تراثي', 'classic', 20, true),
(3, 'palestinian-halba', 'الحلبة الفلسطينية', 17, '/manus-storage/halba_b11748a8.jpeg', 'حلبة بزيت زيتون بكر، بنكهة حلبة وسمسم محمّص.', 'تراثي', 'classic', 20, true),
(4, 'palestinian-cinnamon-roll', 'مبشورة', 19, '/manus-storage/sinabon2_167424f4.jpeg', 'لفائف قرفة هشة بصوص كريمي فاخر.', 'مخبوز', 'classic', 20, true),
(5, 'date-kaak', 'ليالي لبنان', 16, '/manus-storage/kaak-asawer_68d26c1d.jpeg', 'كعك أساور نابلسي محشو تمر ملوكي وسمسم بلدي.', 'تمر', 'classic', 20, true),
(6, 'date-maamoul', 'كعك أساور بالتمر الفاخر', 16, '/manus-storage/maamoul_afd864a4.jpeg', 'معمول هش يذوب بالفم، محشو تمر معطر بالهيل.', 'تمر', 'classic', 20, true),
(7, 'petit-four', 'معمول بالتمر الفاخر', 17, '/manus-storage/petitfour_35f57354.jpeg', 'بيتفور زبدة فاخر بمربى مشمش طبيعي.', 'مخبوز', 'classic', 20, true),
(8, 'maqroute', 'بيتفور', 17, '/manus-storage/maqrouta_061f8551.jpeg', 'مقروطة محمّصة بالسمن البلدي وتمر مجدول.', 'تمر', 'classic', 20, true),
(9, 'mabshoura', 'مقروطة', 16, '/manus-storage/mabshoura_04f58b59.jpeg', 'مبشورة هشة بطبقات تفاح وقرفة.', 'مخبوز', 'classic', 20, true),
(10, 'family-box', 'بوكس العائلة', 100, '/manus-storage/family-box_a8f9c1f4.webp', 'تشكيلة عائلية من حلويات حكاية حلا الفلسطينية.', 'عائلي', 'family', 20, true),
(11, 'gift-box', 'بوكس إهداء من القلب', 100, '/manus-storage/gift-box_8e41bbed.webp', 'تشكيلة حلويات أنيقة مناسبة للإهداء والمناسبات.', 'عائلي', 'family', 20, true),
(12, 'cheesecake-box', 'بوكس تشيز كيك', 100, '/manus-storage/cheesecake-box_2a61d9d0.webp', 'قطع تشيز كيك مزينة بالفراولة والشوكولاتة.', 'عائلي', 'family', 20, true),
(13, 'dessert-pizza', 'بيتزا حكاية حلا', 100, '/manus-storage/dessert-pizza_b0e54ce9.webp', 'بيتزا حلوة بثلاث نكهات ظاهرة في الصورة: الشوكولاتة والفراولة والفستق.', 'عائلي', 'family', 20, true),
(14, 'cheesecake-duo', 'بوكس تشيز كيك بالفراولة والشوكولاتة', 100, '/manus-storage/cheesecake-duo_ec25fe70.webp', 'بوكس يضم تشيز كيك بالفراولة وتشيز كيك بالشوكولاتة.', 'عائلي', 'family', 20, true),
(15, 'premium-cake', 'كيك فاخر', 100, '/manus-storage/premium-cake_2bd487df.webp', 'كيك فاخر بطبقات كريمة ومزين بالفواكه.', 'عائلي', 'family', 20, true)
on conflict (id) do update set slug=excluded.slug, name=excluded.name, price=excluded.price, image=excluded.image, description=excluded.description, tag=excluded.tag, collection=excluded.collection, active=true, updated_at=now();

insert into public.site_content (id, content) values ('main', '{}'::jsonb) on conflict (id) do nothing;
