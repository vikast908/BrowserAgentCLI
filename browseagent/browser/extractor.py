"""Extract structured data from DOM elements."""

from __future__ import annotations

import json
import logging
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def extract_table_data(page: Page, table_selector: str = "table") -> list[dict[str, str]]:
    """Extract data from an HTML table into a list of row dicts.

    Uses the first row (or <thead>) as column headers.
    """
    return await page.evaluate("""(selector) => {
        const table = document.querySelector(selector);
        if (!table) return [];

        const rows = Array.from(table.querySelectorAll('tr'));
        if (rows.length < 2) return [];

        // Get headers from first row or thead
        const headerRow = table.querySelector('thead tr') || rows[0];
        const headers = Array.from(headerRow.querySelectorAll('th, td')).map(
            cell => cell.innerText.trim()
        );

        // Get data rows
        const dataRows = table.querySelector('thead') ? rows : rows.slice(1);
        return Array.from(dataRows).map(row => {
            const cells = Array.from(row.querySelectorAll('td'));
            const obj = {};
            cells.forEach((cell, i) => {
                if (i < headers.length) {
                    obj[headers[i]] = cell.innerText.trim();
                }
            });
            return obj;
        }).filter(obj => Object.keys(obj).length > 0);
    }""", table_selector)


async def extract_list_items(
    page: Page,
    container_selector: str,
    fields: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Extract repeating items from a container.

    Args:
        container_selector: CSS selector for the repeating item containers.
        fields: Optional mapping of field_name → CSS selector (relative to each container).
                If None, extracts the full text of each item.
    """
    if fields is None:
        return await page.evaluate("""(selector) => {
            const items = document.querySelectorAll(selector);
            return Array.from(items).map(el => ({
                text: el.innerText.trim()
            }));
        }""", container_selector)

    return await page.evaluate("""([selector, fields]) => {
        const items = document.querySelectorAll(selector);
        return Array.from(items).map(container => {
            const record = {};
            for (const [key, sel] of Object.entries(fields)) {
                const el = container.querySelector(sel);
                record[key] = el ? el.innerText.trim() : '';
            }
            return record;
        }).filter(obj => Object.values(obj).some(v => v));
    }""", [container_selector, fields])


async def extract_text_content(page: Page, selector: str) -> str:
    """Extract the text content of a single element."""
    element = await page.query_selector(selector)
    if element:
        return (await element.inner_text()).strip()
    return ""


async def extract_links(page: Page, container_selector: str | None = None) -> list[dict[str, str]]:
    """Extract all links (text + href) from a container or the whole page."""
    sel = container_selector or "body"
    return await page.evaluate("""(selector) => {
        const container = document.querySelector(selector);
        if (!container) return [];
        const links = container.querySelectorAll('a[href]');
        return Array.from(links).map(a => ({
            text: a.innerText.trim(),
            href: a.href
        })).filter(l => l.text);
    }""", sel)


async def extract_by_llm_data(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pass through data extracted by the LLM in the 'done' action.

    The LLM can return structured data directly. This function normalizes it.
    """
    if not data:
        return []

    # Ensure all records have consistent keys
    all_keys: set[str] = set()
    for record in data:
        all_keys.update(record.keys())

    normalized = []
    for record in data:
        normalized.append({k: record.get(k, "") for k in sorted(all_keys)})

    return normalized
