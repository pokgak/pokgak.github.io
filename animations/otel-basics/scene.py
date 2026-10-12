"""Animate one request becoming an OpenTelemetry trace waterfall."""

import manimgx as m


m.config.pixel_width = 1280
m.config.pixel_height = 720
m.config.frame_rate = 30
m.config.background_color = "#0B1020"


BACKGROUND = "#0B1020"
TEXT = "#F8FAFC"
MUTED = "#A8B4C7"
GRID = "#334155"
ROOT = "#38BDF8"
CALCULATE = "#C4B5FD"
API = "#FBBF24"
DO = "#6EE7B7"


class OtelTraceWaterfall(m.Scene):
    """Show span creation and closure in execution order."""

    def construct(self) -> None:
        title = m.Text(
            "How one request becomes a trace",
            font="sans-serif",
            font_size=42,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to([0, 3.5, 0])
        status = m.Text(
            "A trace records nested work over time",
            font="sans-serif",
            font_size=27,
            weight=m.NORMAL,
            color=MUTED,
        ).move_to([0, 2.92, 0])
        self.play(m.FadeIn(title), m.FadeIn(status), run_time=0.8)

        request_box, request_text = self.card(
            "Request", center=[-5.15, 2.1, 0], width=1.65, color=TEXT
        )
        entry_box, entry_text = self.card(
            "entryPoint",
            center=[-1.35, 2.1, 0],
            width=2.15,
            color=ROOT,
            font="monospace",
        )
        route = m.Arrow(
            [-4.15, 2.1, 0],
            [-2.62, 2.1, 0],
            buff=0,
            color=MUTED,
            stroke_width=4,
        )
        packet = m.Dot([-4.05, 2.1, 0], radius=0.11, color=TEXT).set_z_index(4)
        self.play(
            m.FadeIn(request_box),
            m.FadeIn(request_text),
            m.Create(route),
            m.FadeIn(entry_box),
            m.FadeIn(entry_text),
            run_time=0.6,
        )
        new_status = self.status("One request enters the application")
        self.remove(status)
        self.add(new_status)
        self.play(
            m.FadeIn(packet),
            packet.animate.move_to([-2.62, 2.1, 0]),
            run_time=0.9,
            rate_func=m.linear,
        )
        status = new_status

        timeline_start = -2.15
        timeline_end = 5.7
        axis_y = 1.25
        axis = m.Line(
            [timeline_start, axis_y, 0],
            [timeline_end, axis_y, 0],
            color=GRID,
            stroke_width=3,
        )
        spans_heading = m.Text(
            "SPANS",
            font="sans-serif",
            font_size=23,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to([-5.55, axis_y, 0])
        zero = m.Text(
            "start",
            font="sans-serif",
            font_size=22,
            weight=m.MEDIUM,
            color=TEXT,
        ).next_to(
            axis.get_start(), m.UP, buff=0.1
        )
        time = m.Text(
            "time  →",
            font="sans-serif",
            font_size=22,
            weight=m.MEDIUM,
            color=TEXT,
        ).next_to(
            axis.get_end(), m.UP, buff=0.1
        )
        row_lines = m.VGroup(
            *(
                m.Line(
                    [timeline_start, y - 0.35, 0],
                    [timeline_end, y - 0.35, 0],
                    color=GRID,
                    stroke_width=1,
                )
                for y in [0.62, -0.25, -1.12, -1.99]
            )
        )
        self.play(
            m.Create(axis),
            m.FadeIn(spans_heading),
            m.FadeIn(zero),
            m.FadeIn(time),
            m.FadeIn(row_lines),
            run_time=0.6,
        )

        root_label = self.span_label("entryPoint", [-5.45, 0.62, 0], TEXT)
        calculate_label = self.span_label(
            "↳  calculateSomething", [-5.08, -0.25, 0], TEXT
        )
        api_label = self.span_label("↳  callApi", [-4.72, -1.12, 0], TEXT)
        do_label = self.span_label("↳  doSomething", [-5.08, -1.99, 0], TEXT)

        root = self.span(timeline_start, 0.62, ROOT)
        calculate = self.span(-0.82, -0.25, CALCULATE)
        api = self.span(0.22, -1.12, API)
        do = self.span(2.08, -1.99, DO)

        new_status = self.status("entryPoint opens the root span")
        self.remove(status)
        self.add(new_status)
        self.add(root[0])
        self.play(
            m.FadeIn(root_label),
            m.GrowFromCenter(root[1]),
            root[0].animate.stretch_to_fit_width(0.65, about_edge=m.LEFT),
            run_time=0.8,
        )
        status = new_status

        new_status = self.status("calculateSomething opens a child span")
        self.remove(status)
        self.add(new_status)
        self.add(calculate[0])
        self.play(
            m.FadeIn(calculate_label),
            m.GrowFromCenter(calculate[1]),
            root[0].animate.stretch_to_fit_width(1.75, about_edge=m.LEFT),
            calculate[0].animate.stretch_to_fit_width(0.48, about_edge=m.LEFT),
            run_time=0.9,
        )
        status = new_status

        new_status = self.status("callApi opens inside calculateSomething")
        self.remove(status)
        self.add(new_status)
        self.add(api[0])
        self.play(
            m.FadeIn(api_label),
            m.GrowFromCenter(api[1]),
            root[0].animate.stretch_to_fit_width(2.8, about_edge=m.LEFT),
            calculate[0].animate.stretch_to_fit_width(1.42, about_edge=m.LEFT),
            api[0].animate.stretch_to_fit_width(0.26, about_edge=m.LEFT),
            run_time=0.9,
        )
        status = new_status

        api_end = self.end_cap(1.08, -1.12, API)
        new_status = self.status("callApi closes first")
        self.remove(status)
        self.add(new_status)
        self.play(
            root[0].animate.stretch_to_fit_width(3.35, about_edge=m.LEFT),
            calculate[0].animate.stretch_to_fit_width(1.75, about_edge=m.LEFT),
            api[0].animate.stretch_to_fit_width(0.86, about_edge=m.LEFT),
            m.Create(api_end),
            run_time=0.8,
        )
        status = new_status

        calculate_end = self.end_cap(1.45, -0.25, CALCULATE)
        new_status = self.status("calculateSomething closes next")
        self.remove(status)
        self.add(new_status)
        self.play(
            root[0].animate.stretch_to_fit_width(4.0, about_edge=m.LEFT),
            calculate[0].animate.stretch_to_fit_width(2.27, about_edge=m.LEFT),
            m.Create(calculate_end),
            run_time=0.8,
        )
        status = new_status

        new_status = self.status("doSomething opens as a sibling span")
        self.remove(status)
        self.add(new_status)
        self.add(do[0])
        self.play(
            m.FadeIn(do_label),
            m.GrowFromCenter(do[1]),
            root[0].animate.stretch_to_fit_width(5.05, about_edge=m.LEFT),
            do[0].animate.stretch_to_fit_width(0.55, about_edge=m.LEFT),
            run_time=0.9,
        )
        status = new_status

        do_end = self.end_cap(4.38, -1.99, DO)
        new_status = self.status("doSomething closes")
        self.remove(status)
        self.add(new_status)
        self.play(
            root[0].animate.stretch_to_fit_width(6.55, about_edge=m.LEFT),
            do[0].animate.stretch_to_fit_width(2.3, about_edge=m.LEFT),
            m.Create(do_end),
            run_time=0.9,
        )
        status = new_status

        root_end = self.end_cap(5.45, 0.62, ROOT)
        new_status = self.status(
            "entryPoint closes last — trace complete",
            color=TEXT,
            weight=m.SEMIBOLD,
        )
        self.remove(status)
        self.add(new_status)
        complete = m.Text(
            "Final trace waterfall: parent → child, start time, and duration",
            font="sans-serif",
            font_size=24,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to([0.45, 2.1, 0])
        complete_rule = m.Line(
            [-5.6, 1.65, 0], [5.7, 1.65, 0], color=GRID, stroke_width=2
        )
        self.play(
            m.FadeOut(request_box),
            m.FadeOut(request_text),
            m.FadeOut(route),
            m.FadeOut(entry_box),
            m.FadeOut(entry_text),
            m.FadeOut(packet),
            root[0].animate.stretch_to_fit_width(7.1, about_edge=m.LEFT),
            run_time=0.45,
        )
        self.add(complete)
        self.play(
            root[0].animate.stretch_to_fit_width(7.6, about_edge=m.LEFT),
            m.Create(root_end),
            m.Create(complete_rule),
            run_time=0.75,
        )
        self.wait(1.8)

    @staticmethod
    def card(
        label: str,
        center: list[float],
        width: float,
        color: str,
        font: str = "sans-serif",
    ) -> tuple[m.RoundedRectangle, m.Text]:
        box = m.RoundedRectangle(
            width=width,
            height=0.62,
            corner_radius=0.14,
            color=color,
            fill_color=BACKGROUND,
            fill_opacity=1,
            stroke_width=2,
        ).move_to(center)
        text = (
            m.Text(
                label,
                font=font,
                font_size=25,
                weight=m.MEDIUM,
                color=TEXT,
            )
            .move_to(center)
            .set_z_index(2)
        )
        return box, text

    @staticmethod
    def status(
        label: str, color: str = MUTED, weight: str = m.MEDIUM
    ) -> m.Text:
        return m.Text(
            label,
            font="sans-serif",
            font_size=27,
            weight=weight,
            color=color,
        ).move_to([0, 2.92, 0])

    @staticmethod
    def span_label(label: str, center: list[float], color: str) -> m.Text:
        text = m.Text(
            label,
            font="monospace",
            font_size=25,
            weight=m.MEDIUM,
            color=color,
        )
        text.move_to(center)
        text.align_to([center[0], center[1], 0], m.LEFT)
        return text

    @staticmethod
    def span(start: float, y: float, color: str) -> tuple[m.Rectangle, m.Dot]:
        body = m.Rectangle(
            width=0.08,
            height=0.42,
            color=color,
            fill_color=color,
            fill_opacity=0.82,
            stroke_width=1,
        ).move_to([start + 0.04, y, 0])
        start_dot = m.Dot([start, y, 0], radius=0.09, color=TEXT).set_z_index(3)
        return body, start_dot

    @staticmethod
    def end_cap(x: float, y: float, color: str) -> m.Line:
        return m.Line(
            [x, y - 0.26, 0],
            [x, y + 0.26, 0],
            color=color,
            stroke_width=5,
        ).set_z_index(3)
