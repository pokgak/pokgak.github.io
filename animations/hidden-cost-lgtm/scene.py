"""Visualize cross-AZ transfer amplification for one LGTM telemetry batch."""

from __future__ import annotations

import manimgx as m


m.config.background_color = "#07111F"

BG = "#07111F"
LANE_FILL = "#0D1B2A"
LANE_STROKE = "#294057"
NODE_FILL = "#13263A"
TEXT = "#F8FAFC"
MUTED = "#9FB0C3"
BLUE = "#38BDF8"
GREEN = "#4ADE80"
RED = "#FB7185"
AMBER = "#FBBF24"
PURPLE = "#A78BFA"

LANE_Y = {"A": 1.55, "B": 0.0, "C": -1.55}
X = {
    "collector": -5.55,
    "load_balancer": -3.70,
    "ingress": -1.75,
    "distributor": 0.35,
    "ingester": 5.20,
}


def point(component: str, az: str) -> list[float]:
    """Return the center of a component in an availability-zone lane."""
    return [X[component], LANE_Y[az], 0]


def component(label: str, position: list[float], color: str) -> m.VGroup:
    """Create a compact pipeline component."""
    box = m.RoundedRectangle(
        width=1.28,
        height=0.68,
        corner_radius=0.14,
        stroke_color=color,
        stroke_width=2.4,
        fill_color=NODE_FILL,
        fill_opacity=1,
    )
    name = m.Text(
        label,
        font="sans-serif",
        font_size=16,
        weight=m.MEDIUM,
        color=TEXT,
        line_spacing=-0.10,
    )
    return m.VGroup(box, name).move_to(position)


def telemetry_batch() -> m.VGroup:
    """Create the single telemetry batch carried along the pipeline."""
    body = m.RoundedRectangle(
        width=0.48,
        height=0.24,
        corner_radius=0.08,
        stroke_color=BLUE,
        stroke_width=2,
        fill_color="#0C4A6E",
        fill_opacity=1,
    )
    samples = m.VGroup(
        m.Dot([-0.13, 0, 0], radius=0.032, color=TEXT),
        m.Dot([0, 0, 0], radius=0.032, color=TEXT),
        m.Dot([0.13, 0, 0], radius=0.032, color=TEXT),
    )
    return m.VGroup(body, samples)


def route(start: list[float], end: list[float], color: str) -> m.Arrow:
    """Draw a route between component edges."""
    return m.Arrow(
        start,
        end,
        buff=0.74,
        color=color,
        stroke_width=4.5,
        tip_length=0.16,
    )


def travel(batch: m.Mobject, start: list[float], end: list[float], seconds: float = 1.0) -> m.MoveAlongPath:
    """Move a batch above node labels along the indicated component route."""
    offset = 0.48 * m.UP
    batch.move_to(start + offset)
    return m.MoveAlongPath(
        batch,
        m.Line(start + offset, end + offset),
        run_time=seconds,
        rate_func=m.smooth,
    )


def counter(value: int, color: str = TEXT) -> m.Text:
    """Create the current transfer total at the fixed counter position."""
    return m.Text(
        str(value),
        font="sans-serif",
        font_size=34,
        weight=m.BOLD,
        color=color,
    ).move_to([6.45, -2.48, 0])


def increment_badge(position: list[float], text: str = "+1") -> m.VGroup:
    """Mark a transfer where a route crosses an AZ boundary."""
    pill = m.RoundedRectangle(
        width=0.76,
        height=0.38,
        corner_radius=0.16,
        stroke_color=RED,
        stroke_width=1.8,
        fill_color=BG,
        fill_opacity=1,
    )
    label = m.Text(text, font="sans-serif", font_size=17, weight=m.MEDIUM, color=RED)
    return m.VGroup(pill, label).move_to(position)


class HiddenCostLGTM(m.Scene):
    """Follow one batch through default and routing-aware LGTM paths."""

    def construct(self) -> None:
        title = m.Text(
            "One telemetry batch through LGTM",
            font="sans-serif",
            font_size=35,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to([0, 3.50, 0])
        subtitle = m.Text(
            "Illustrative route  ·  replication factor 3",
            font="sans-serif",
            font_size=22,
            weight=m.NORMAL,
            color=MUTED,
        ).move_to([0, 2.97, 0])

        self.play(m.Write(title), m.FadeIn(subtitle, shift=0.12 * m.UP), run_time=1.4)
        self.wait(0.8)

        lane_backgrounds = m.VGroup()
        lane_labels = m.VGroup()
        for az, y in LANE_Y.items():
            lane_backgrounds.add(
                m.RoundedRectangle(
                    width=13.00,
                    height=1.25,
                    corner_radius=0.18,
                    stroke_color=LANE_STROKE,
                    stroke_width=1.5,
                    fill_color=LANE_FILL,
                    fill_opacity=1,
                ).move_to([0.30, y, 0])
            )
            lane_labels.add(
                m.Text(
                    f"AZ {az}",
                    font="sans-serif",
                    font_size=17,
                    weight=m.MEDIUM,
                    color=MUTED,
                ).move_to([-6.48, y, 0])
            )

        collector_a = component("Collector", point("collector", "A"), BLUE)
        load_balancers = m.VGroup(
            *[
                component("Load\nbalancer", point("load_balancer", az), PURPLE)
                for az in LANE_Y
            ]
        )
        ingresses = m.VGroup(
            *[component("Ingress", point("ingress", az), AMBER) for az in LANE_Y]
        )
        distributors = m.VGroup(
            *[
                component("Distributor", point("distributor", az), BLUE)
                for az in LANE_Y
            ]
        )
        ingesters = m.VGroup(
            *[component("Ingester", point("ingester", az), GREEN) for az in LANE_Y]
        )
        pipeline = m.VGroup(collector_a, load_balancers, ingresses, distributors, ingesters)

        phase = m.Text(
            "Default routing  ·  affinity off  ·  round-robin service",
            font="sans-serif",
            font_size=22,
            weight=m.SEMIBOLD,
            color=RED,
        ).move_to([0, 2.62, 0])
        meter_label = m.Text(
            "Cross-AZ transfer events:",
            font="sans-serif",
            font_size=20,
            weight=m.MEDIUM,
            color=MUTED,
        ).move_to([4.55, -2.48, 0])
        meter_value = counter(0)

        self.play(
            m.LaggedStart(*[m.FadeIn(lane) for lane in lane_backgrounds], lag_ratio=0.12),
            m.LaggedStart(*[m.FadeIn(label) for label in lane_labels], lag_ratio=0.12),
            run_time=1.0,
        )
        self.play(
            m.LaggedStart(*[m.GrowFromCenter(node) for node in pipeline], lag_ratio=0.04),
            m.FadeIn(phase),
            m.FadeIn(meter_label),
            m.FadeIn(meter_value),
            run_time=1.8,
        )

        batch = telemetry_batch().move_to(point("collector", "A") + 0.48 * m.UP)
        batch_label = m.Text(
            "one batch",
            font="sans-serif",
            font_size=17,
            weight=m.MEDIUM,
            color=BLUE,
        ).move_to([-5.55, 0.77, 0])
        self.play(m.FadeIn(batch, shift=0.18 * m.RIGHT), m.FadeIn(batch_label), run_time=0.7)

        # No client AZ affinity: this example resolves to a load-balancer node in AZ B.
        collector_to_lb_b = route(point("collector", "A"), point("load_balancer", "B"), RED)
        first_crossing = increment_badge([-4.72, 0.84, 0])
        self.play(m.FadeOut(batch_label), m.Create(collector_to_lb_b), run_time=0.5)
        self.play(travel(batch, point("collector", "A"), point("load_balancer", "B"), 1.2))
        meter_1 = counter(1, RED)
        self.play(
            m.FadeIn(first_crossing, shift=0.12 * m.UP),
            m.ReplacementTransform(meter_value, meter_1),
            run_time=0.5,
        )
        meter_value = meter_1

        # The selected load-balancer node forwards to ingress in its own AZ.
        lb_b_to_ingress_b = route(point("load_balancer", "B"), point("ingress", "B"), GREEN)
        same_az = m.Text(
            "same AZ",
            font="sans-serif",
            font_size=18,
            weight=m.MEDIUM,
            color=GREEN,
        ).move_to([-2.72, 0.75, 0])
        self.play(m.Create(lb_b_to_ingress_b), m.FadeIn(same_az), run_time=0.5)
        self.play(travel(batch, point("load_balancer", "B"), point("ingress", "B"), 0.9))

        # A round-robin Kubernetes Service can choose a distributor in another AZ.
        ingress_b_to_distributor_c = route(point("ingress", "B"), point("distributor", "C"), RED)
        second_crossing = increment_badge([-0.70, -0.80, 0])
        self.play(m.Create(ingress_b_to_distributor_c), run_time=0.5)
        self.play(travel(batch, point("ingress", "B"), point("distributor", "C"), 1.2))
        meter_2 = counter(2, RED)
        self.play(
            m.FadeIn(second_crossing, shift=0.12 * m.DOWN),
            m.ReplacementTransform(meter_value, meter_2),
            run_time=0.5,
        )
        meter_value = meter_2

        replication_note = m.Text(
            "ring replication fans out 1 → 3",
            font="sans-serif",
            font_size=18,
            weight=m.MEDIUM,
            color=AMBER,
        ).move_to([0, -2.48, 0])
        self.play(m.FadeIn(replication_note), run_time=0.4)

        distributor_c_to_ingesters = m.VGroup(
            route(point("distributor", "C"), point("ingester", "A"), RED),
            route(point("distributor", "C"), point("ingester", "B"), RED),
            route(point("distributor", "C"), point("ingester", "C"), GREEN),
        )
        replicated_batches = [batch.copy() for _ in range(3)]
        self.play(
            m.FadeOut(batch),
            *[m.FadeIn(copy) for copy in replicated_batches],
            *[m.Create(path) for path in distributor_c_to_ingesters],
            run_time=0.8,
        )
        self.play(
            *[
                travel(copy, point("distributor", "C"), point("ingester", az), 1.5)
                for copy, az in zip(replicated_batches, LANE_Y, strict=True)
            ]
        )
        replication_badges = m.VGroup(
            increment_badge([2.55, 0.30, 0]),
            increment_badge([3.00, -0.88, 0]),
        )
        meter_4 = counter(4, RED)
        self.play(
            m.LaggedStart(*[m.FadeIn(badge) for badge in replication_badges], lag_ratio=0.18),
            m.ReplacementTransform(meter_value, meter_4),
            run_time=0.7,
        )
        meter_value = meter_4
        default_result = m.Text(
            "4 in this default route",
            font="sans-serif",
            font_size=18,
            weight=m.BOLD,
            color=RED,
        ).move_to([0, -2.48, 0])
        self.play(m.ReplacementTransform(replication_note, default_result), run_time=0.4)
        self.wait(1.4)

        default_traces = m.VGroup(
            collector_to_lb_b,
            lb_b_to_ingress_b,
            ingress_b_to_distributor_c,
            distributor_c_to_ingesters,
        )
        default_annotations = m.VGroup(
            first_crossing,
            same_az,
            second_crossing,
            replication_badges,
            default_result,
        )
        aware_phase = m.Text(
            "Routing-aware  ·  AZ affinity  ·  topology-aware service",
            font="sans-serif",
            font_size=22,
            weight=m.SEMIBOLD,
            color=GREEN,
        ).move_to(phase)
        aware_meter_0 = counter(0, GREEN)
        self.play(
            m.FadeOut(default_traces),
            m.FadeOut(default_annotations),
            *[m.FadeOut(copy) for copy in replicated_batches],
            m.ReplacementTransform(phase, aware_phase),
            m.ReplacementTransform(meter_value, aware_meter_0),
            run_time=1.0,
        )
        phase = aware_phase
        meter_value = aware_meter_0

        # Replay the same logical batch with local routing for the hops that support it.
        aware_batch = telemetry_batch().move_to(point("collector", "A") + 0.48 * m.UP)
        aware_routes = m.VGroup(
            route(point("collector", "A"), point("load_balancer", "A"), GREEN),
            route(point("load_balancer", "A"), point("ingress", "A"), GREEN),
            route(point("ingress", "A"), point("distributor", "A"), GREEN),
        )
        local_note = m.Text(
            "local endpoints",
            font="sans-serif",
            font_size=17,
            weight=m.MEDIUM,
            color=GREEN,
        ).move_to([-2.65, 2.32, 0])
        self.play(m.FadeIn(aware_batch), m.FadeIn(local_note), run_time=0.5)
        aware_stops = ("load_balancer", "ingress", "distributor")
        aware_starts = ("collector", "load_balancer", "ingress")
        for visible_route, start, end in zip(aware_routes, aware_starts, aware_stops, strict=True):
            self.play(m.Create(visible_route), run_time=0.35)
            self.play(travel(aware_batch, point(start, "A"), point(end, "A"), 0.75))

        aware_replication_note = m.Text(
            "replication still spans AZs",
            font="sans-serif",
            font_size=18,
            weight=m.MEDIUM,
            color=AMBER,
        ).move_to([0, -2.48, 0])
        aware_replication_routes = m.VGroup(
            route(point("distributor", "A"), point("ingester", "A"), GREEN),
            route(point("distributor", "A"), point("ingester", "B"), RED),
            route(point("distributor", "A"), point("ingester", "C"), RED),
        )
        aware_copies = [aware_batch.copy() for _ in range(3)]
        self.play(
            m.FadeIn(aware_replication_note),
            m.FadeOut(aware_batch),
            *[m.FadeIn(copy) for copy in aware_copies],
            *[m.Create(path) for path in aware_replication_routes],
            run_time=0.8,
        )
        self.play(
            *[
                travel(copy, point("distributor", "A"), point("ingester", az), 1.5)
                for copy, az in zip(aware_copies, LANE_Y, strict=True)
            ]
        )
        aware_badges = m.VGroup(
            increment_badge([2.85, 0.85, 0]),
            increment_badge([2.45, -0.25, 0]),
        )
        meter_2_aware = counter(2, RED)
        self.play(
            m.LaggedStart(*[m.FadeIn(badge) for badge in aware_badges], lag_ratio=0.18),
            m.ReplacementTransform(meter_value, meter_2_aware),
            run_time=0.7,
        )
        meter_value = meter_2_aware
        aware_result = m.Text(
            "2 remain: replicated writes",
            font="sans-serif",
            font_size=18,
            weight=m.BOLD,
            color=AMBER,
        ).move_to([0, -2.48, 0])
        self.play(m.ReplacementTransform(aware_replication_note, aware_result), run_time=0.4)
        self.wait(1.4)

        # End on the comparison and its scope, not on an exact universal multiplier.
        everything_but_titles = m.VGroup(
            lane_backgrounds,
            lane_labels,
            pipeline,
            phase,
            meter_label,
            meter_value,
            aware_routes,
            local_note,
            aware_replication_routes,
            aware_badges,
            aware_result,
            *aware_copies,
        )
        final_title = m.Text(
            "Route locally where the stack allows it",
            font="sans-serif",
            font_size=35,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to(title)
        comparison = m.VGroup(
            m.Text("4", font="sans-serif", font_size=84, weight=m.BOLD, color=RED),
            m.Text("→", font="sans-serif", font_size=56, weight=m.BOLD, color=MUTED),
            m.Text("2", font="sans-serif", font_size=84, weight=m.BOLD, color=GREEN),
        ).arrange(m.RIGHT, buff=0.52).move_to([0, 1.10, 0])
        comparison_label = m.Text(
            "cross-AZ transfer events in this route",
            font="sans-serif",
            font_size=24,
            weight=m.NORMAL,
            color=TEXT,
        ).move_to([0, 0.22, 0])
        fixed_hops = m.VGroup(
            m.Text("AZ affinity", font="sans-serif", font_size=22, weight=m.MEDIUM, color=GREEN),
            m.Text("collector → load balancer", font="sans-serif", font_size=18, weight=m.NORMAL, color=MUTED),
            m.Text("Topology-aware routing", font="sans-serif", font_size=22, weight=m.MEDIUM, color=GREEN),
            m.Text("ingress → distributor", font="sans-serif", font_size=18, weight=m.NORMAL, color=MUTED),
        ).arrange_in_grid(rows=2, cols=2, buff=(0.85, 0.26)).move_to([0, -1.00, 0])
        remains = m.Text(
            "Cross-AZ ring replication remains",
            font="sans-serif",
            font_size=24,
            weight=m.SEMIBOLD,
            color=AMBER,
        ).move_to([0, -2.02, 0])
        caveat = m.Text(
            "Actual amplification depends on placement and replication factor.",
            font="sans-serif",
            font_size=18,
            weight=m.NORMAL,
            color=MUTED,
        ).move_to([0, -2.74, 0])

        self.play(
            m.FadeOut(everything_but_titles),
            m.ReplacementTransform(title, final_title),
            m.FadeOut(subtitle),
            run_time=1.0,
        )
        self.play(m.LaggedStart(*[m.FadeIn(item) for item in comparison], lag_ratio=0.15), run_time=0.9)
        self.play(m.FadeIn(comparison_label), m.FadeIn(fixed_hops), run_time=0.8)
        self.play(m.FadeIn(remains), m.FadeIn(caveat), run_time=0.7)
        self.wait(3.2)
