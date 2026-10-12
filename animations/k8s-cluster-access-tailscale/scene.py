"""Six-step Tailscale request flow for the Kubernetes access article."""

import manimgx as m


m.config.background_color = "#07111F"

BACKGROUND = "#07111F"
PANEL = "#102033"
PANEL_BORDER = "#334155"
TEXT = "#F8FAFC"
MUTED = "#A8B5C7"
DNS = "#FBBF24"
TAILSCALE = "#38BDF8"
REQUEST = "#34D399"
CONTROL = "#C4B5FD"


def card(
    center: tuple[float, float, float],
    width: float,
    short: str,
    label: str,
    detail: str,
    accent: str,
    detail_font: str = "sans-serif",
) -> m.VGroup:
    """Build a labelled network node with a redundant text identifier."""
    panel = m.RoundedRectangle(
        width=width,
        height=1.45,
        corner_radius=0.18,
        color=PANEL_BORDER,
        stroke_width=2,
        fill_color=PANEL,
        fill_opacity=1,
    )
    badge_text = m.Text(
        short,
        font="monospace",
        font_size=16,
        weight=m.MEDIUM,
        color=accent,
    )
    name = m.Text(
        label,
        font="sans-serif",
        font_size=19,
        weight=m.MEDIUM,
        color=TEXT,
    )
    secondary = m.Text(
        detail,
        font=detail_font,
        font_size=16,
        weight=m.NORMAL,
        color=MUTED,
    )
    contents = m.VGroup(badge_text, name, secondary).arrange(
        m.DOWN,
        buff=0.12,
    )
    contents.move_to(panel)
    return m.VGroup(panel, contents).move_to(center)


def path_arrow(start: m.Mobject, end: m.Mobject, color: str) -> m.Arrow:
    """Connect adjacent cards without drawing through their labels."""
    return m.Arrow(
        start.get_right(),
        end.get_left(),
        buff=0.08,
        color=color,
        stroke_width=4,
        max_tip_length_to_length_ratio=0.18,
    )


def legend_item(line: m.Mobject, label: str) -> m.VGroup:
    text = m.Text(
        label,
        font="sans-serif",
        font_size=16,
        weight=m.MEDIUM,
        color=MUTED,
    )
    return m.VGroup(line, text).arrange(m.RIGHT, buff=0.12)


class KubernetesAccessFlow(m.Scene):
    """Explain DNS setup and the six live-request steps without narration."""

    def construct(self) -> None:
        title = m.Text(
            "From a Tailscale client to a Kubernetes Pod",
            font="sans-serif",
            font_size=38,
            weight=m.SEMIBOLD,
            color=TEXT,
        ).move_to([0, 3.55, 0])
        subtitle = m.Text(
            "prometheus.k8s.pokgak.xyz  →  10.43.170.163",
            font="monospace",
            font_size=20,
            weight=m.NORMAL,
            color=MUTED,
        ).move_to([0, 3.04, 0])

        cloudflare = card(
            (-3.6, 1.8, 0),
            2.25,
            "DNS",
            "Cloudflare DNS",
            "A → 10.43.170.163",
            DNS,
            detail_font="monospace",
        )
        external_dns = card(
            (0.35, 1.8, 0),
            2.25,
            "SYNC",
            "external-dns",
            "setup / control plane",
            CONTROL,
        )
        control_path = m.DashedLine(
            external_dns.get_left(),
            cloudflare.get_right(),
            buff=0.08,
            dash_length=0.13,
            dashed_ratio=0.55,
            color=CONTROL,
            stroke_width=3,
        ).add_tip(tip_length=0.16, tip_width=0.16)
        control_label = m.Text(
            "creates A record",
            font="sans-serif",
            font_size=15,
            weight=m.MEDIUM,
            color=CONTROL,
        ).next_to(control_path, m.UP, buff=0.09)
        not_in_path = m.Text(
            "NOT IN REQUEST DATA PATH",
            font="sans-serif",
            font_size=15,
            weight=m.SEMIBOLD,
            color=CONTROL,
        ).next_to(external_dns, m.DOWN, buff=0.12)

        client = card(
            (-5.85, -0.4, 0),
            1.85,
            "VPN",
            "Remote client",
            "on Tailscale",
            TAILSCALE,
        )
        route = card(
            (-2.85, -0.4, 0),
            2.25,
            "CIDR",
            "Advertised route",
            "10.43.0.0/16",
            TAILSCALE,
            detail_font="monospace",
        )
        router = card(
            (0.05, -0.4, 0),
            2.05,
            "RTR",
            "Subnet router",
            "Tailscale node",
            TAILSCALE,
        )
        service = card(
            (3.0, -0.4, 0),
            2.25,
            "SVC",
            "ClusterIP Service",
            "10.43.170.163",
            REQUEST,
            detail_font="monospace",
        )
        pod = card(
            (5.9, -0.4, 0),
            1.75,
            "POD",
            "Pod",
            "endpoint",
            REQUEST,
        )

        route_path = path_arrow(client, route, REQUEST)
        tunnel_path = path_arrow(route, router, REQUEST)
        service_path = path_arrow(router, service, REQUEST)
        pod_path = path_arrow(service, pod, REQUEST)
        data_paths = m.VGroup(route_path, tunnel_path, service_path, pod_path)

        dns_query = m.Arrow(
            client.get_top() + 0.15 * m.RIGHT,
            cloudflare.get_bottom() + 0.15 * m.LEFT,
            buff=0.08,
            color=DNS,
            stroke_width=3,
            max_tip_length_to_length_ratio=0.14,
        )
        dns_answer = m.Arrow(
            cloudflare.get_bottom() + 0.18 * m.RIGHT,
            client.get_top() + 0.18 * m.LEFT,
            buff=0.08,
            color=DNS,
            stroke_width=3,
            max_tip_length_to_length_ratio=0.14,
        )

        status_panel = m.RoundedRectangle(
            width=12.5,
            height=0.78,
            corner_radius=0.15,
            color=PANEL_BORDER,
            stroke_width=2,
            fill_color=PANEL,
            fill_opacity=1,
        ).move_to([0, -2.35, 0])

        def status(
            step: str,
            message: str,
            accent: str,
            *,
            emphasis: bool = False,
        ) -> m.VGroup:
            step_tag = m.Text(
                step,
                font="sans-serif",
                font_size=18,
                weight=m.BOLD if emphasis else m.MEDIUM,
                color=accent,
            )
            message_text = m.Text(
                message,
                font="sans-serif",
                font_size=23,
                weight=m.BOLD if emphasis else m.NORMAL,
                color=TEXT,
            )
            return m.VGroup(step_tag, message_text).arrange(
                m.RIGHT,
                buff=0.3,
            ).move_to(status_panel)

        setup_status = status(
            "SETUP",
            "external-dns creates the record before requests begin",
            CONTROL,
        )
        steps = [
            status("STEP 1", "Resolve the service name with Cloudflare DNS", DNS),
            status("STEP 2", "DNS returns ClusterIP 10.43.170.163", DNS),
            status("STEP 3", "The IP matches the advertised 10.43.0.0/16 route", TAILSCALE),
            status("STEP 4", "Tailscale sends the packet to the subnet router", TAILSCALE),
            status("STEP 5", "The router forwards it to the ClusterIP Service", REQUEST),
            status("STEP 6", "The Service load-balances the request to a Pod", REQUEST),
        ]
        conclusion = status(
            "RESULT",
            "Private Service access for authorized Tailscale clients",
            REQUEST,
            emphasis=True,
        )

        request_legend = legend_item(
            m.Line(m.LEFT * 0.25, m.RIGHT * 0.25, color=REQUEST, stroke_width=4),
            "request traffic",
        )
        dns_legend = legend_item(
            m.Line(m.LEFT * 0.25, m.RIGHT * 0.25, color=DNS, stroke_width=4),
            "DNS query / answer",
        )
        control_legend = legend_item(
            m.DashedLine(
                m.LEFT * 0.25,
                m.RIGHT * 0.25,
                dash_length=0.08,
                color=CONTROL,
                stroke_width=3,
            ),
            "setup / control plane",
        )
        legend = m.VGroup(request_legend, dns_legend, control_legend).arrange(
            m.RIGHT,
            buff=0.7,
        ).move_to([0, -1.55, 0])

        self.play(m.FadeIn(title), m.FadeIn(subtitle, shift=m.UP * 0.1), run_time=0.8)
        self.play(
            m.LaggedStart(
                *[
                    m.FadeIn(node, shift=m.UP * 0.08)
                    for node in [cloudflare, external_dns, client, route, router, service, pod]
                ],
                lag_ratio=0.08,
            ),
            m.FadeIn(status_panel),
            m.FadeIn(setup_status),
            m.FadeIn(legend),
            run_time=1.2,
        )
        self.play(
            m.Create(control_path),
            m.FadeIn(control_label),
            m.FadeIn(not_in_path),
            m.Circumscribe(cloudflare, color=CONTROL),
            run_time=1.2,
        )
        self.wait(0.8)

        self.play(m.FadeOut(setup_status), run_time=0.18)
        self.play(
            m.FadeIn(steps[0]),
            m.Create(dns_query),
            m.Circumscribe(client, color=DNS),
            run_time=1.0,
        )
        query_packet = m.Dot(dns_query.get_start(), radius=0.09, color=TEXT)
        self.add(query_packet)
        self.play(m.MoveAlongPath(query_packet, dns_query), run_time=0.9)
        self.play(m.FadeOut(query_packet), m.Circumscribe(cloudflare, color=DNS), run_time=0.45)

        self.play(m.FadeOut(steps[0]), run_time=0.18)
        self.play(
            m.FadeIn(steps[1]),
            m.Create(dns_answer),
            run_time=0.55,
        )
        answer_packet = m.Dot(dns_answer.get_start(), radius=0.09, color=TEXT)
        answer_label = m.Text(
            "10.43.170.163",
            font="monospace",
            font_size=17,
            weight=m.MEDIUM,
            color=DNS,
        ).next_to(dns_answer, m.RIGHT, buff=0.08)
        self.add(answer_packet)
        self.play(
            m.MoveAlongPath(answer_packet, dns_answer),
            m.FadeIn(answer_label),
            run_time=1.0,
        )
        self.play(m.FadeOut(answer_packet), m.Circumscribe(client, color=DNS), run_time=0.45)

        self.play(m.FadeOut(steps[1]), run_time=0.18)
        self.play(
            m.FadeIn(steps[2]),
            m.Create(route_path),
            run_time=0.55,
        )
        route_packet = m.Dot(route_path.get_start(), radius=0.09, color=TEXT)
        self.add(route_packet)
        self.play(m.MoveAlongPath(route_packet, route_path), run_time=0.9)
        self.play(m.FadeOut(route_packet), m.Circumscribe(route, color=TAILSCALE), run_time=0.45)

        self.play(m.FadeOut(steps[2]), run_time=0.18)
        self.play(
            m.FadeIn(steps[3]),
            m.Create(tunnel_path),
            run_time=0.55,
        )
        tunnel_packet = m.Dot(tunnel_path.get_start(), radius=0.09, color=TEXT)
        self.add(tunnel_packet)
        self.play(m.MoveAlongPath(tunnel_packet, tunnel_path), run_time=0.9)
        self.play(m.FadeOut(tunnel_packet), m.Circumscribe(router, color=TAILSCALE), run_time=0.45)

        self.play(m.FadeOut(steps[3]), run_time=0.18)
        self.play(
            m.FadeIn(steps[4]),
            m.Create(service_path),
            run_time=0.55,
        )
        service_packet = m.Dot(service_path.get_start(), radius=0.09, color=TEXT)
        self.add(service_packet)
        self.play(m.MoveAlongPath(service_packet, service_path), run_time=0.9)
        self.play(m.FadeOut(service_packet), m.Circumscribe(service, color=REQUEST), run_time=0.45)

        self.play(m.FadeOut(steps[4]), run_time=0.18)
        self.play(
            m.FadeIn(steps[5]),
            m.Create(pod_path),
            run_time=0.55,
        )
        pod_packet = m.Dot(pod_path.get_start(), radius=0.09, color=TEXT)
        self.add(pod_packet)
        self.play(m.MoveAlongPath(pod_packet, pod_path), run_time=0.9)
        self.play(m.FadeOut(pod_packet), m.Circumscribe(pod, color=REQUEST), run_time=0.45)

        self.play(m.FadeOut(steps[5]), run_time=0.18)
        self.play(
            m.FadeIn(conclusion),
            m.ShowPassingFlash(data_paths.copy().set_color(TEXT), time_width=0.35),
            run_time=1.2,
        )
        self.wait(2.0)
