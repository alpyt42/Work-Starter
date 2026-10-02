---
name: brand-deck
description: Build a PowerPoint deck from an approved brand template and private brand recipe using the reusable deck-kit engine.
---

# brand-deck

The reusable workflow lives here. The private brand register is `brain/.data/brands/brands.md`; recipes and guides live in `brain/.data/brands/<brand>/`. Original templates and other large brand assets live in local `artifacts/<project>/brand-kit/`. Read the register, brand guide, and project page before drafting content.

1. Confirm the audience, message, language, and brand from the project context. If the brand kit is missing, request the actual template instead of recreating it from memory.
2. Write a YAML deck plan in `agents/<project>/<date-slug>/`, using the recipes and meaningful icon names in the brand card. Preserve source or verification markers and never invent figures. Vary layouts to suit the content. Build it with `repos/personal/deck-kit`, passing the private brand recipe to the engine. A failed engine QA blocks delivery.
3. Render the result and inspect every slide for overflow, font substitution, and missing assets. Leave margin when the renderer cannot reproduce embedded brand fonts. Fix the plan and rebuild as needed; do not hand-edit generated PowerPoint files.
4. Put the final `.pptx` in `artifacts/<project>/<slug>/` with a README recording the source plan, template, build command, and review status. Artifacts remain local and are not restored by this repository.

If a brand recipe needs improvement, update it in the private brain and record the reason in the project page. Keep the engine generic and free of client assets.

For a new brand, get the actual template, inspect useful slides with the engine, create a private recipe and guide, and test every recipe before adding it to the register. Ask the owner before changing the private register.
