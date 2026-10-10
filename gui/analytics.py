"""Closed-scenario filters, field analytics and validation tabs."""

from __future__ import annotations

import pandas as pd

from performance_analytics import (
    build_field_performance,
    build_signal_validation,
    build_stock_ranking,
)
from gui.config import (
    CLOSED_SCENARIO_COLUMN_BOUNDS,
    FIELD_DISPLAY_COLUMNS,
    RANKING_DISPLAY_COLUMNS,
    SIGNAL_VALIDATION_DISPLAY_COLUMNS,
)
from gui.formatting import (
    active_scenario_tag,
    field_performance_for_display,
    ranking_for_display,
    scan_event_tag,
    signal_validation_for_display,
)
from gui.scan_results import (
    _horizon_months,
    filter_closed_scenarios,
    validate_chart_strength_range,
)
from gui.tables import populate_table


class AnalyticsMixin:
    """Closed-scenario filters, field analytics and validation tabs. Mixed into BuyPointApp; relies on its attributes."""

    def _apply_scan_event_tags(self, data: pd.DataFrame) -> None:
        for item, (_, row) in zip(self.scan_tree.get_children(), data.iterrows()):
            tag = scan_event_tag(row.get("단계"), row.get("결과"))
            self.scan_tree.item(item, tags=(tag,) if tag else ())

    def _apply_active_scenario_tags(self, data: pd.DataFrame) -> None:
        for item, (_, row) in zip(self.active_tree.get_children(), data.iterrows()):
            tag = active_scenario_tag(row.get("현재상태"))
            self.active_tree.item(item, tags=(tag,) if tag else ())

    def _reset_closed_scenario_filters(self) -> None:
        self.closed_grade_filter_enabled_var.set(False)
        self.closed_grade_filter_var.set("우선검토")
        self.closed_score_filter_enabled_var.set(False)
        self.closed_score_min_var.set("70")
        self.closed_score_max_var.set("100")
        self._refresh_closed_scenario_view()

    def _refresh_closed_scenario_view(self) -> None:
        for entry_name in ("closed_score_min_entry", "closed_score_max_entry"):
            entry = getattr(self, entry_name, None)
            if entry is not None:
                entry.state(["!invalid"])

        try:
            minimum, maximum = validate_chart_strength_range(
                self.closed_score_min_var.get(),
                self.closed_score_max_var.get(),
                enabled=self.closed_score_filter_enabled_var.get(),
            )
        except ValueError as exc:
            for entry_name in ("closed_score_min_entry", "closed_score_max_entry"):
                entry = getattr(self, entry_name, None)
                if entry is not None:
                    entry.state(["invalid"])
            self.closed_filter_status_var.set(str(exc))
            return

        display = filter_closed_scenarios(
            self.latest_closed_scenarios,
            grade_enabled=self.closed_grade_filter_enabled_var.get(),
            grade=self.closed_grade_filter_var.get(),
            score_enabled=self.closed_score_filter_enabled_var.get(),
            minimum_score=minimum,
            maximum_score=maximum,
        )
        populate_table(
            self.closed_scenario_tree,
            display,
            column_bounds=CLOSED_SCENARIO_COLUMN_BOUNDS,
        )
        self._apply_history_tags(display, tree=self.closed_scenario_tree)
        self.closed_filter_status_var.set(
            f"표시 {len(display):,}건 / 전체 {len(self.latest_closed_scenarios):,}건"
        )

    def _refresh_signal_validation(self) -> None:
        if not self.latest_cycles_by_ticker:
            populate_table(
                self.validation_tree,
                pd.DataFrame(columns=SIGNAL_VALIDATION_DISPLAY_COLUMNS),
            )
            self.validation_status_var.set("통합 스캔 후 신호 효과를 확인할 수 있습니다.")
            return
        grade_by_key = {
            key: str(detail.get("grade", ""))
            for key, detail in self.chart_strength_details.items()
        }
        # Only the ranked companies: watchlist tickers stay out of these statistics.
        analysis_tickers = {
            company.ticker.upper() for company in self.latest_analysis_companies
        }
        validation = build_signal_validation(
            {
                ticker: cycles
                for ticker, cycles in self.latest_cycles_by_ticker.items()
                if ticker in analysis_tickers
            },
            grade_by_key,
        )
        populate_table(self.validation_tree, signal_validation_for_display(validation))
        date_text = (
            self.latest_scan_date.strftime("%Y-%m-%d")
            if self.latest_scan_date is not None
            else "미정"
        )
        self.validation_status_var.set(
            f"분석 기준일 {date_text} / {len(self.latest_cycles_by_ticker)}종목의 "
            "확정된 매수 성공 사례 기준"
        )

    def _on_field_control_change(self, _event) -> None:
        self._refresh_field_analytics(reset_selection=False)

    def _on_field_select(self, _event) -> None:
        selected = self.field_tree.selection()
        if not selected:
            return
        field = self.field_tree.set(selected[0], "분야")
        if not field:
            return
        self.selected_field = field
        self._refresh_field_ranking()

    def _refresh_field_analytics(self, reset_selection: bool = False) -> None:
        if not self.latest_analysis_companies:
            populate_table(self.field_tree, pd.DataFrame(columns=FIELD_DISPLAY_COLUMNS))
            populate_table(self.ranking_tree, pd.DataFrame(columns=RANKING_DISPLAY_COLUMNS))
            return

        level = self.field_level_var.get()
        horizon = _horizon_months(self.field_horizon_var.get())
        fields = build_field_performance(
            self.latest_analysis_companies,
            self.latest_cycles_by_ticker,
            self.latest_classifications,
            level,
            horizon,
        )
        display = field_performance_for_display(fields)
        populate_table(self.field_tree, display)

        available_fields = display["분야"].tolist() if not display.empty else []
        if reset_selection or self.selected_field not in available_fields:
            self.selected_field = available_fields[0] if available_fields else None
        if self.selected_field is not None:
            for item in self.field_tree.get_children():
                if self.field_tree.set(item, "분야") == self.selected_field:
                    self.field_tree.selection_set(item)
                    self.field_tree.focus(item)
                    break
        self._refresh_field_ranking()

        analyzed = sum(
            ticker in self.latest_cycles_by_ticker
            for ticker in (company.ticker.upper() for company in self.latest_analysis_companies)
        )
        total = len(self.latest_analysis_companies)
        excluded = total - analyzed
        date_text = (
            self.latest_scan_date.strftime("%Y-%m-%d")
            if self.latest_scan_date is not None
            else "미정"
        )
        self.field_status_var.set(
            f"분석 기준일 {date_text} / 현재 Top 100 구성 종목 기준 / "
            f"정상 분석 {analyzed}종목 / 데이터 오류 제외 {excluded}종목 / "
            f"{horizon}개월 성과"
        )

    def _refresh_field_ranking(self) -> None:
        if not self.selected_field or not self.latest_analysis_companies:
            populate_table(self.ranking_tree, pd.DataFrame(columns=RANKING_DISPLAY_COLUMNS))
            return
        ranking = build_stock_ranking(
            self.latest_analysis_companies,
            self.latest_cycles_by_ticker,
            self.latest_classifications,
            self.field_level_var.get(),
            self.selected_field,
            _horizon_months(self.field_horizon_var.get()),
            self.ranking_sort_var.get(),
        )
        populate_table(self.ranking_tree, ranking_for_display(ranking))
