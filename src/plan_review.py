#!/usr/bin/env python3
"""
OneShot Assignment 06: Plan Review

Two gap passes: (1) verify against actual code, (2) verify against applicable
engineering practices. Call for Help requests evidence, doesn't infer.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GapItem:
    """A gap found during plan review."""
    area: str
    description: str
    pass_number: int  # 1 = grounding, 2 = best practice
    status: str  # pass, fail, call_for_help
    evidence: str


@dataclass
class PlanReviewResult:
    """Result of plan review."""
    pass1_results: list = field(default_factory=list)
    pass2_results: list = field(default_factory=list)
    call_for_help: list = field(default_factory=list)
    all_pass: bool = False
    gaps_remaining: int = 0


class PlanReview:
    """Plan review with two gap passes."""

    def pass1_grounding(self, plan_items: list, actual_code: dict) -> list:
        """Pass 1: verify each plan item against actual code."""
        results = []
        for item in plan_items:
            area = item.get("area", "")
            evidence = actual_code.get(area, "")
            if evidence:
                results.append(GapItem(area=area, description=item.get("description", ""),
                                       pass_number=1, status="pass", evidence=evidence))
            else:
                results.append(GapItem(area=area, description=item.get("description", ""),
                                       pass_number=1, status="fail", evidence="No code found"))
        return results

    def pass2_best_practice(self, plan_items: list, practices: dict) -> list:
        """Pass 2: verify against applicable engineering practices."""
        results = []
        for item in plan_items:
            area = item.get("area", "")
            practice = practices.get(area, "")
            if practice:
                results.append(GapItem(area=area, description=item.get("description", ""),
                                       pass_number=2, status="pass", evidence=practice))
            else:
                results.append(GapItem(area=area, description=item.get("description", ""),
                                       pass_number=2, status="call_for_help",
                                       evidence="No best practice found — requesting evidence"))
        return results

    def review(self, plan_items: list, actual_code: dict, practices: dict) -> PlanReviewResult:
        """Run both gap passes."""
        pass1 = self.pass1_grounding(plan_items, actual_code)
        pass2 = self.pass2_best_practice(plan_items, practices)

        call_for_help = [g for g in pass2 if g.status == "call_for_help"]
        gaps = [g for g in pass1 + pass2 if g.status == "fail"]

        return PlanReviewResult(
            pass1_results=pass1,
            pass2_results=pass2,
            call_for_help=call_for_help,
            all_pass=len(gaps) == 0,
            gaps_remaining=len(gaps),
        )
