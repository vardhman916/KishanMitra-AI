import os
import json
import asyncio
import sys
from typing import Dict, Any, Optional, List, Union

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    Frame,
)

URL = "https://farmextensionmanager.com/fertilizer-calculator"
CACHE_DIR = os.path.join("data", "fert_calc_cache_v1")
STATIC_OPTIONS_PATH = os.path.join(CACHE_DIR, "options.json")


class FertCalcLiveToolV1:
    """
    LIVE fertilizer calculator automation via Playwright.
    Dropdown options are loaded from local JSON (options.json).
    Website is used only for calculation.
    """

    LABELS = {
        "crop_group": "Select the crop group",
        "crop_name": "Select the name of crop",
        "condition": "Select the condition of application",
        "soil_type": "Type of soil in the area",
        "organic_carbon": "Amount of Nitrogen as percent of organic carbon",
        "available_p": "Amount of available Phosphorous",
        "available_k": "Amount of available Potassium",
    }

    def __init__(self, headless: bool = True):
        self.headless = headless
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._ensure_windows_event_loop_policy()

    @staticmethod
    def _ensure_windows_event_loop_policy() -> None:
        if sys.platform != "win32":
            return
        try:
            policy = asyncio.get_event_loop_policy()
            if not isinstance(policy, asyncio.WindowsProactorEventLoopPolicy):
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    # ------------------------
    # Static options
    # ------------------------
    def load_static_options(self) -> Dict[str, Any]:
        if not os.path.exists(STATIC_OPTIONS_PATH):
            raise FileNotFoundError(
                f"Missing {STATIC_OPTIONS_PATH}. Create it at data/fert_calc_cache_v1/options.json"
            )
        with open(STATIC_OPTIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------
    # Context / iframe handler
    # ------------------------
    def _get_form_context(self, page: Page) -> Union[Page, Frame]:
        """
        Return the page OR the iframe that contains the fertilizer form (<select>).
        Fixes intermittent: selects scanned=0.
        """
        # Try main page first
        try:
            page.wait_for_selector("select", timeout=12000)
            return page
        except Exception:
            pass

        # Scan frames
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                if fr.locator("select").count() > 0:
                    return fr
            except Exception:
                continue

        # Last attempt
        try:
            page.wait_for_timeout(1500)
            page.wait_for_selector("select", timeout=12000)
            return page
        except Exception:
            return page

    # ------------------------
    # Dropdown select (robust)
    # ------------------------
    def _safe_select(self, ctx: Union[Page, Frame], label_key: str, value: str, wait_ms: int = 400) -> None:
        """
        Robust selection:
        A) Find label text and select in same row/table
        B) Fallback: choose select by option-probe
        """
        label_text = self.LABELS[label_key]

        # A) label -> nearest row -> first select
        try:
            label_node = ctx.locator(f":text-matches('{label_text}', 'i')").first
            label_node.wait_for(state="visible", timeout=15000)
            row = label_node.locator("xpath=ancestor::tr[1]")
            sel = row.locator("select").first
            sel.wait_for(state="visible", timeout=15000)
            sel.select_option(label=value)
            ctx.wait_for_timeout(wait_ms)
            return
        except Exception:
            pass

        # B) probe selects by options
        selects = ctx.locator("select")
        count = selects.count()
        if count == 0:
            raise PlaywrightTimeoutError(
                f"No <select> elements found while selecting '{label_text}'. Possibly iframe or blocked."
            )

        # probe: for crop_group use first 3 static values, else probe the value itself
        try:
            static = self.load_static_options()
            if label_key == "crop_group":
                probe = static.get("crop_group", [])[:3]
            else:
                probe = [value]
        except Exception:
            probe = [value]

        def option_texts(sel) -> List[str]:
            opts = sel.locator("option")
            out = []
            for j in range(opts.count()):
                t = (opts.nth(j).inner_text() or "").strip()
                if t:
                    out.append(t)
            return out

        found = None
        best = -1
        for i in range(count):
            sel = selects.nth(i)
            try:
                if not sel.is_visible():
                    continue
                texts = option_texts(sel)
                score = sum(1 for p in probe if p in texts)
                if score > best:
                    best = score
                    found = sel
            except Exception:
                continue

        if found is None or best <= 0:
            raise PlaywrightTimeoutError(
                f"Could not find dropdown for '{label_text}'. Selects scanned={count}. Probe={probe}."
            )

        found.select_option(label=value)
        ctx.wait_for_timeout(wait_ms)

    # ------------------------
    # Fill numeric inputs safely (NO buttons)
    # ------------------------
    def _fill_numeric_inputs(self, ctx: Union[Page, Frame], number_of_plants: float, area_value: float) -> None:
        """
        The site has editable <input> fields, but also buttons as <input type="button">.
        We fill only editable inputs.
        If we find:
          - 2 editable inputs: fill plants then area
          - 1 editable input: fill it with number_of_plants (most common)
        """
        # Editable inputs only
        editable = ctx.locator(
            "input:not([type]),"
            "input[type='text'],"
            "input[type='number'],"
            "input[type='tel']"
        )
        n = editable.count()

        # Filter visible + enabled + editable
        good = []
        for i in range(min(n, 80)):
            inp = editable.nth(i)
            try:
                if not inp.is_visible():
                    continue
                t = (inp.get_attribute("type") or "").lower().strip()
                if t in {"button", "submit", "reset", "hidden", "checkbox", "radio", "file", "image"}:
                    continue
                if inp.is_disabled():
                    continue
                good.append(inp)
            except Exception:
                continue

        if not good:
            # fallback: try any visible input that is not button/submit
            all_inputs = ctx.locator("input")
            for i in range(min(all_inputs.count(), 120)):
                inp = all_inputs.nth(i)
                try:
                    if not inp.is_visible():
                        continue
                    t = (inp.get_attribute("type") or "").lower().strip()
                    if t in {"button", "submit", "reset", "hidden", "checkbox", "radio", "file", "image"}:
                        continue
                    if inp.is_disabled():
                        continue
                    good.append(inp)
                except Exception:
                    continue

        if not good:
            return

        # Fill first with plants
        try:
            good[0].fill(str(number_of_plants))
        except Exception:
            pass

        # Fill second with area (if present)
        if len(good) >= 2:
            try:
                good[1].fill(str(area_value))
            except Exception:
                pass

    # ------------------------
    # Click recommendation button (handles <input type="button">)
    # ------------------------
    def _click_recommend_button(self, page: Page, ctx: Union[Page, Frame], mode: str) -> None:
        """
        On this site, buttons are often:
          <input type="button" value="Generate Blanket Recommendation" onclick="...">
        So we must locate BOTH:
          - input[type=button][value=...]
          - button:has-text(...)
          - text match fallback
        """
        text = "Soil Test Based Recommendation" if mode == "soil_test" else "Generate Blanket Recommendation"
        targets = [ctx, page]

        for target in targets:
            # 1) input button by value
            locators = [
                target.locator(f"input[type='button'][value='{text}']").first,
                target.locator(f"input[type='submit'][value='{text}']").first,
                target.locator(f"button:has-text('{text}')").first,
                target.get_by_role("button", name=text).first,
                target.locator(f":text-matches('{text}', 'i')").first,
            ]

            for btn in locators:
                try:
                    if btn.count() == 0:
                        continue
                    btn.wait_for(state="visible", timeout=20000)
                    btn.scroll_into_view_if_needed()
                    target.wait_for_timeout(200)
                    try:
                        btn.click(timeout=20000)
                    except Exception:
                        handle = btn.element_handle()
                        if handle:
                            target.evaluate("(el) => el.click()", handle)
                    return
                except Exception:
                    continue

        raise PlaywrightTimeoutError(f"Could not find/click recommendation control: {text}")

    # ------------------------
    # Extract ONLY the first Fertilizer Recommendation table
    # ------------------------
    def _extract_fertilizer_recommendation_html(self, ctx: Union[Page, Frame]) -> Optional[str]:
        """
        Return the OUTER HTML of the table containing the 'Fertilizer Recommendation' heading.
        This preserves merged headers/colspans exactly like the website.
        """
        heading = ctx.locator(":text-matches('Fertilizer Recommendation', 'i')").first
        if heading.count() == 0:
            return None

        # Usually the heading is inside the table, so ancestor::table[1] is correct
        table = heading.locator("xpath=ancestor::table[1]")
        if table.count() == 0:
            # fallback: first table after heading
            table = heading.locator("xpath=following::table[1]")

        if table.count() == 0:
            return None

        try:
            return table.evaluate("el => el.outerHTML")
        except Exception:
            return None

    # ------------------------
    # MAIN FUNCTION
    # ------------------------
    def generate_recommendation(
        self,
        crop_group: str,
        crop_name: str,
        condition: str,
        Number_of_plants: float,
        area_value: float,
        soil_type: Optional[str] = None,
        organic_carbon: Optional[str] = None,
        available_p: Optional[str] = None,
        available_k: Optional[str] = None,
        mode: str = "blanket",
    ) -> str:
        """
        Runs the fertilizer calculator live and returns ONLY the first output table
        ('Fertilizer Recommendation') as HTML for exact formatting in Streamlit.
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()
                page.set_default_timeout(60000)
                page.set_default_navigation_timeout(120000)

                page.goto(URL, wait_until="domcontentloaded")

                ctx = self._get_form_context(page)

                # ensure dropdown exists
                ctx.wait_for_selector("select", timeout=30000)

                # 1) dropdowns
                self._safe_select(ctx, "crop_group", crop_group, 800)
                self._safe_select(ctx, "crop_name", crop_name, 600)
                self._safe_select(ctx, "condition", condition, 500)

                # 2) numeric inputs
                self._fill_numeric_inputs(ctx, Number_of_plants, area_value)

                # 3) optional soil-test dropdowns
                def set_opt(k: str, v: Optional[str]):
                    if v:
                        try:
                            self._safe_select(ctx, k, v, 250)
                        except Exception:
                            pass

                set_opt("soil_type", soil_type)
                set_opt("organic_carbon", organic_carbon)
                set_opt("available_p", available_p)
                set_opt("available_k", available_k)

                # 4) click recommendation
                self._click_recommend_button(page, ctx, mode)

                # 5) wait for output heading (more reliable)
                try:
                    ctx.locator(":text-matches('Fertilizer Recommendation', 'i')").first.wait_for(
                        state="visible", timeout=20000
                    )
                except Exception:
                    pass

                html_table = self._extract_fertilizer_recommendation_html(ctx)
                browser.close()

                if html_table:
                    return json.dumps({"type": "html_table", "html": html_table}, ensure_ascii=False)

                return "Recommendation generated, but could not extract output."

        except Exception as exc:
            return f"Live recommendation failed. Error: {type(exc).__name__}: {exc}"
