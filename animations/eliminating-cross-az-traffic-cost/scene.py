"""Animate the request path from cross-AZ routing to AZ-local routing."""

import manimgx as m


m.config.background_color = "#07111F"

TEXT = "#E5EEF8"
MUTED = "#BCCADB"
LANE = "#334155"
CLIENT = "#94A3B8"
NLB = "#38BDF8"
INGRESS = "#A78BFA"
BACKEND = "#FBBF24"
CROSS_AZ = "#FB7185"
LOCAL = "#4ADE80"
WARNING = "#F59E0B"

ROWS = (1.75, 0.87, -0.01)
X_POSITIONS = (-4.75, -2.05, 0.65, 4.35)


def node(label: str, x: float, y: float, width: float, color: str) -> m.VGroup:
    box = m.RoundedRectangle(
        width=width,
        height=0.62,
        corner_radius=0.12,
        color=color,
        fill_opacity=0.12,
        stroke_width=2.2,
    ).move_to([x, y, 0])
    text = m.Text(
        label,
        font="sans-serif",
        weight=m.MEDIUM,
        font_size=19,
        color=TEXT,
    ).move_to(box)
    return m.VGroup(box, text)


def arrow(start: m.Mobject, end: m.Mobject, color: str) -> m.Arrow:
    return m.Arrow(
        start,
        end,
        buff=0.12,
        color=color,
        stroke_width=4.5,
        max_tip_length_to_length_ratio=0.12,
    )


def copy_text(
    text: str,
    color: str = TEXT,
    size: float = 21,
    weight: str = m.NORMAL,
) -> m.Text:
    return m.Text(
        text,
        font="sans-serif",
        weight=weight,
        font_size=size,
        color=color,
    ).move_to([0, -1.00, 0])


class CrossAzOptimization(m.Scene):
    def construct(self) -> None:
        title = m.Text(
            "Eliminating cross-AZ request traffic",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=36,
            color=TEXT,
        ).move_to([0, 3.55, 0])
        state = m.Text(
            "BEFORE · one request crosses three AZ boundaries",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=25,
            color=CROSS_AZ,
        ).move_to([0, 3.02, 0])

        headers = m.VGroup(
            *[
                m.Text(
                    label,
                    font="sans-serif",
                    weight=m.MEDIUM,
                    font_size=16,
                    color=MUTED,
                ).move_to([x, 2.52, 0])
                for label, x in zip(
                    ("CLIENT", "NLB NODE", "INGRESS-NGINX", "BACKEND POD"),
                    X_POSITIONS,
                )
            ]
        )

        lanes = m.VGroup()
        clients: list[m.VGroup] = []
        nlbs: list[m.VGroup] = []
        ingresses: list[m.VGroup] = []
        backends: list[m.VGroup] = []

        for index, y in enumerate(ROWS, start=1):
            lane = m.RoundedRectangle(
                width=13.0,
                height=0.82,
                corner_radius=0.14,
                color=LANE,
                fill_opacity=0.06,
                stroke_width=1.5,
            ).move_to([0, y, 0])
            az_label = m.Text(
                f"AZ {index}",
                font="sans-serif",
                weight=m.MEDIUM,
                font_size=16,
                color=MUTED,
            ).move_to([-6.0, y + 0.22, 0])
            lanes.add(m.VGroup(lane, az_label))
            clients.append(node("client", X_POSITIONS[0], y, 1.35, CLIENT))
            nlbs.append(node("NLB", X_POSITIONS[1], y, 1.25, NLB))
            ingresses.append(node("ingress", X_POSITIONS[2], y, 1.60, INGRESS))
            backends.append(node("pod", X_POSITIONS[3], y, 1.30, BACKEND))

        nodes = m.VGroup(*clients, *nlbs, *ingresses, *backends)
        detail = copy_text(
            "Default choices can send every application hop to another AZ",
            CROSS_AZ,
        )

        self.play(m.FadeIn(title, shift=0.15 * m.DOWN), run_time=0.55)
        self.play(m.FadeIn(lanes), m.FadeIn(headers), run_time=0.65)
        self.play(m.FadeIn(nodes, shift=0.12 * m.UP), run_time=0.70)
        self.play(m.FadeIn(state), m.FadeIn(detail), run_time=0.45)

        cross_paths = [
            arrow(clients[0][0], nlbs[2][0], CROSS_AZ),
            arrow(nlbs[2][0], ingresses[1][0], CROSS_AZ),
            arrow(ingresses[1][0], backends[2][0], CROSS_AZ),
        ]
        cross_details = (
            "CROSS-AZ · client in AZ 1 → NLB node in AZ 3",
            "CROSS-AZ · NLB node in AZ 3 → ingress in AZ 2",
            "CROSS-AZ · ingress in AZ 2 → backend pod in AZ 3",
        )
        packet = m.Dot(cross_paths[0].get_start(), radius=0.11, color=CROSS_AZ)

        for index, (path, words) in enumerate(zip(cross_paths, cross_details)):
            next_detail = copy_text(words, CROSS_AZ)
            self.play(m.FadeOut(detail), run_time=0.12)
            self.play(
                m.GrowArrow(path),
                m.FadeIn(next_detail),
                run_time=0.28,
            )
            detail = next_detail
            if index == 0:
                self.play(m.FadeIn(packet), run_time=0.15)
            else:
                packet.move_to(path.get_start())
            self.play(
                m.MoveAlongPath(packet, path),
                run_time=0.80,
                rate_func=m.linear,
            )
        self.wait(0.70)

        step_one = m.Text(
            "STEP 1 · AZ-affine NLB DNS response",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=25,
            color=LOCAL,
        ).move_to(state)
        step_one_detail = copy_text(
            "AZ-affine DNS favors an NLB IP in the client's AZ",
            LOCAL,
        )
        self.play(
            m.FadeOut(m.VGroup(*cross_paths, packet)),
            m.FadeOut(state),
            m.FadeOut(detail),
            run_time=0.20,
        )
        self.play(m.FadeIn(step_one), m.FadeIn(step_one_detail), run_time=0.35)
        state, detail = step_one, step_one_detail

        local_paths = [
            arrow(clients[0][0], nlbs[0][0], LOCAL),
            arrow(nlbs[0][0], ingresses[0][0], LOCAL),
            arrow(ingresses[0][0], backends[0][0], LOCAL),
        ]

        self.play(m.GrowArrow(local_paths[0]), run_time=0.40)
        packet = m.Dot(local_paths[0].get_start(), radius=0.11, color=LOCAL)
        self.play(m.FadeIn(packet), run_time=0.15)
        self.play(
            m.MoveAlongPath(packet, local_paths[0]),
            run_time=0.85,
            rate_func=m.linear,
        )
        self.play(m.FadeOut(packet), m.Indicate(nlbs[0]), run_time=0.30)

        step_two = m.Text(
            "STEP 2 · route to a local ingress target",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=25,
            color=LOCAL,
        ).move_to(state)
        step_two_detail = copy_text(
            "Cross-zone load balancing off → NLB forwards only to local ingress targets",
            LOCAL,
            19,
        )
        self.play(m.FadeOut(state), m.FadeOut(detail), run_time=0.15)
        self.play(
            m.FadeIn(step_two),
            m.FadeIn(step_two_detail),
            m.GrowArrow(local_paths[1]),
            run_time=0.35,
        )
        state, detail = step_two, step_two_detail
        packet = m.Dot(local_paths[1].get_start(), radius=0.11, color=LOCAL)
        self.play(m.FadeIn(packet), run_time=0.15)
        self.play(
            m.MoveAlongPath(packet, local_paths[1]),
            run_time=0.85,
            rate_func=m.linear,
        )
        self.play(m.FadeOut(packet), m.Indicate(ingresses[0]), run_time=0.30)

        step_three = m.Text(
            "STEP 3 · PreferClose favors a local backend",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=25,
            color=LOCAL,
        ).move_to(state)
        step_three_detail = copy_text(
            "ingress uses Service ClusterIP · PreferClose favors a local endpoint",
            LOCAL,
            19,
        )
        self.play(m.FadeOut(state), m.FadeOut(detail), run_time=0.15)
        self.play(
            m.FadeIn(step_three),
            m.FadeIn(step_three_detail),
            m.GrowArrow(local_paths[2]),
            run_time=0.35,
        )
        state, detail = step_three, step_three_detail
        packet = m.Dot(local_paths[2].get_start(), radius=0.11, color=LOCAL)
        self.play(m.FadeIn(packet), run_time=0.15)
        self.play(
            m.MoveAlongPath(packet, local_paths[2]),
            run_time=0.85,
            rate_func=m.linear,
        )
        self.play(m.FadeOut(packet), m.Indicate(backends[0]), run_time=0.30)

        other_local_paths = [
            arrow(clients[row][0], nlbs[row][0], LOCAL)
            for row in (1, 2)
        ] + [
            arrow(nlbs[row][0], ingresses[row][0], LOCAL)
            for row in (1, 2)
        ] + [
            arrow(ingresses[row][0], backends[row][0], LOCAL)
            for row in (1, 2)
        ]
        after = m.Text(
            "AFTER · application hops prefer the selected AZ",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=25,
            color=LOCAL,
        ).move_to(state)
        result = copy_text(
            "NO CROSS-AZ HOPS while healthy local endpoints are available",
            LOCAL,
            20,
            m.BOLD,
        )
        self.play(m.FadeOut(state), m.FadeOut(detail), run_time=0.15)
        self.play(
            m.FadeIn(after),
            m.FadeIn(result),
            run_time=0.30,
        )
        state, detail = after, result
        self.play(
            *[m.GrowArrow(path) for path in other_local_paths],
            run_time=0.95,
        )

        caveat_box = m.RoundedRectangle(
            width=12.5,
            height=1.15,
            corner_radius=0.16,
            color=WARNING,
            fill_opacity=0.10,
            stroke_width=2.0,
        ).move_to([0, -1.095, 0])
        result_line = m.Text(
            "NO CROSS-AZ HOPS while healthy local endpoints are available",
            font="sans-serif",
            weight=m.BOLD,
            font_size=17,
            color=LOCAL,
        ).move_to([0, -0.72, 0])
        caveat_title = m.Text(
            "RELIABILITY CAVEAT",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=16,
            color=WARNING,
        ).move_to([0, -0.97, 0])
        caveat_line_one = m.Text(
            "Each AZ needs healthy ingress targets; otherwise requests can fail.",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=15,
            color=TEXT,
        ).move_to([0, -1.24, 0])
        caveat_line_two = m.Text(
            "PreferClose can fall back across AZs; skew can still overload one AZ.",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=15,
            color=TEXT,
        ).move_to([0, -1.49, 0])
        caveat = m.VGroup(
            caveat_box,
            result_line,
            caveat_title,
            caveat_line_one,
            caveat_line_two,
        )
        self.play(m.FadeOut(detail), run_time=0.20)
        self.play(m.FadeIn(caveat, shift=0.12 * m.UP), run_time=0.55)
        self.wait(4.5)
