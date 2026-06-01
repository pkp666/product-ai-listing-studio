# product-ai-listing-studio

AI product listing and cross-border commerce content studio.

`product-ai-listing-studio` helps turn product photos and basic product facts into structured listing data, ecommerce copy, platform-specific fields, product images, and short selling-video assets. It is built around a staged workflow for sellers, operators, and creators who need to prepare product content for platforms such as Amazon, Shopify, TikTok Shop, Pinduoduo, and other marketplace-style channels.

## Workflow

The product flow follows six practical stages:

1. **Basic information input**: upload real product photos and fill in product name, material, size, shipping origin, company, and price.
2. **AI product detail enrichment**: analyze images and basic fields to generate selling points, titles, descriptions, specs, keywords, SEO tags, and target audience notes.
3. **Platform field mapping**: adapt universal product data into marketplace-specific forms such as Amazon bullet points, Shopify rich descriptions, TikTok Shop short titles, or PDD category fields.
4. **One-click content generation**: generate product copy, product main images, detail images, listing text, and scene-based product descriptions.
5. **Selling-video generation**: create short video scripts and trigger video/image generation workflows for product promotion.
6. **Listing data storage and publishing preparation**: save field data, generated assets, and listing drafts for browser-plugin or manual publishing workflows.

## Features

- Streamlit UI for staged product listing work.
- Product field schema, SKU matrix helpers, and export utilities.
- AI-assisted product title, selling point, description, keyword, and SEO generation.
- Vision analysis for uploaded product images.
- Platform field mapping with example PDD category mapping data.
- Coze workflow hooks for product main images, detail images, and selling-video generation.
- Yunwu / GRS image and video generation wrappers.
- Remotion template project for product video composition.
- Local-first outputs: generated images, videos, and saved listing drafts stay out of Git by default.

## Repository Layout

```text
app.py                  Main Streamlit app
llm.py                  LLM and vision-call wrapper
ziduan.py               Product data model and SKU helpers
prompt.py               Product enrichment prompts
prompt_pdd.py           PDD listing prompt and mapping helpers
prompt_video.py         Selling-video prompt helpers
listing.py              Local product/listing persistence
image_gen.py            Image generation helpers
video_gen.py            Video generation helpers
coze_workflow.py        Generic Coze workflow driver
cozedaihuo.py           Selling-video Coze workflow wrapper
platform_maps/          Platform field mapping examples
re/my-video/            Remotion product-video template
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

For the Remotion template:

```powershell
cd re/my-video
npm install
npm run dev
```

## Configuration

Copy `.env.example` to `.env` and fill only the services you plan to use.

```env
YUNWU_API_KEY=
GRSAI_API_KEY=
PT_IMAGE_RELAY_BASE_URL=
PT_IMAGE_RELAY_URL=
COZE_TOKEN=
COZE_MIHE_KEY=
COZE_WORKFLOW_ZHUTU_ID=
COZE_WORKFLOW_XIANGXITU_ID=
COZE_WORKFLOW_XIANGXITU2_ID=
COZE_WORKFLOW_VIDEO_ID=
```

The open-source version intentionally does not include private API keys, Coze PATs, workflow IDs, image relay servers, generated images, videos, or local output data.

## Keywords

AI ecommerce, product listing, cross-border ecommerce, marketplace automation, product copywriting, AI product description, product image generation, product video generation, listing optimizer, Amazon listing, Shopify product description, TikTok Shop, Pinduoduo, PDD listing, SKU generator, SEO keywords, product content pipeline, Coze workflow, Remotion video, Streamlit app.

中文关键词：AI电商、商品上架、跨境电商、商品文案、商品详情页、AI生成主图、AI生成详情图、带货视频、上架字段映射、SKU矩阵、Amazon Listing、Shopify商品描述、TikTok Shop、拼多多上架、SEO关键词、商品内容自动化。

## Security Notice

This repository was prepared for public release by moving provider tokens, workflow IDs, and private relay URLs into environment variables. Any key that existed in local source files before publication should be treated as compromised and rotated at the provider.

## License

MIT
