import copy
from typing import Any, Dict, List, Union


def convert_xyplot(lineplot: Dict[str, Any], kind='line') -> Dict[str, Any]:
    """
    Converts a line plot item to an XY plot item, preserving relevant properties.
    """
    x_var = lineplot['data']['x'][0]
    x_data = lineplot['data']['x']
    y1_data = lineplot['data'].get('y1', [])
    y2_data = lineplot['data'].get('y2', [])

    features = [{
        'type': kind,
        'x': x_var,
        'y': 'Value',
        'colors': 'Series'
    }]
    entries = []
    y_labels = [
        lineplot.get('y1-label', ''), lineplot.get('y2-label', '')
    ]
    # separate plots for y1 and y2 data, if present
    if len(y2_data) > 0:
        style = 'col-md-6'
        aspect_ratio = 16/9
    else:
        style = 'col-md-12'
        aspect_ratio = 32/12

    for k, y_data in enumerate([y1_data, y2_data]):
        data = []
        if not y_data:
            continue

        x_label = x_data[0]
        y_label = y_labels[k]
        for i, x_val in enumerate(x_data):
            if i == 0:
                continue    # skip header row
            for j, y_series in enumerate(y_data):
                y_label = y_series[0]
                data.append({
                    x_var: x_val,
                    'Value': y_series[i],
                    'Series': y_label
                })

        entries.append({
            'title': lineplot.get("title", ""),
            'description': lineplot.get("description", ""),
            'kind': 'xyplot',
            'aspect-ratio': aspect_ratio,
            'style': style,
            'scheme': lineplot.get("scheme", "Live8"),
            'x-scale': lineplot['data'].get("x-scale", "linear"),
            'y-scale': lineplot['data'].get("y-scale", "linear"),
            'x-label': x_label,
            'y-label': y_label,
            'features': features,
            'data': data,
            'notes': lineplot.get("notes", "")
        })
    return entries


def convert_table(table: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a table item to a new format, preserving relevant properties.
    """

    return {
        'title': table.get("title", ""),
        'kind': 'table',
        'style': table.get("style", "col-md-12"),
        'header': table.get("header", "column row"),
        'description': table.get("description", ""),
        'notes': table.get("notes", ""),
        'data': [table.get("data", [])]
    }


def translate_report(old_report: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Translates report data from the old formats to the new format.

    Handles:
      1. Single dictionary schema (e.g., 'old-report.json').
      2. Multi-section list schema (e.g., 'old-report_2.json'), where each item
         represents a section containing content items, markdown descriptions, or charts.
    """
    # Normalize input to list of section dicts
    if isinstance(old_report, dict):
        raw_sections = [old_report]
        doc_title = old_report.get("title", "")
        doc_desc = old_report.get("description", "")
    elif isinstance(old_report, list):
        raw_sections = old_report
        # Derive document-level metadata from the primary entry
        doc_title = raw_sections[0].get("title", "") if raw_sections else ""
        doc_desc = ""
    else:
        raise TypeError("Expected old_report to be a dict or list of dicts.")

    translated_sections = []

    for section in raw_sections:
        sec_title = section.get("title", "")
        sec_desc = section.get("description", "")
        sec_items = []

        # If section contains text description without content items
        if sec_desc and not section.get("content"):
            sec_items.append({
                "title": sec_title,
                "description": sec_desc,
                "kind": "richtext",
                "style": "col-md-12",
                "notes": section.get("notes", "")
            })

        for item in section.get("content", []):
            # Convert lineplot items to xyplot items
            if item.get("kind") == "lineplot":
                trans_items = convert_xyplot(item, kind='line')
            elif item.get("kind") == "scatterplot":
                trans_items = convert_xyplot(item, kind='points')
            elif item.get("kind") == "table":
                trans_items = [convert_table(item)]
            else:
                kind = item.get("kind", "")
                trans_item = copy.deepcopy(item)
                trans_item.setdefault("description", "")
                if kind in ("columns", "bars", "donut", "histogram"):
                    trans_item.setdefault("style", "col-md-6")
                else:
                    trans_item.setdefault("style", "col-md-12")
                trans_items = [trans_item]

            sec_items.extend(trans_items)

        translated_sections.append({
            "title": sec_title,
            "style": "row",
            "theme": "default",
            "content": sec_items
        })

    return {
        "title": doc_title,
        "description": doc_desc,
        "sections": translated_sections
    }