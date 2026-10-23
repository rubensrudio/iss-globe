import plotly.graph_objects as go

from iss_globe import style_globe


def build_triangulation_figure(title: str, anchors, truth, estimates):
    """Globe with the known points, lines of sight, the true point and the estimates.

    anchors:   [(name, lat, lon)] known positions (satellites' subpoints or stations)
    truth:     (name, lat, lon, alt_km) the point being located
    estimates: [(label, lat, lon, alt_km, error_m)]
    """
    t_name, t_lat, t_lon, t_alt = truth
    fig = go.Figure()

    line_lat, line_lon = [], []
    for _, lat, lon in anchors:
        line_lat += [lat, t_lat, None]
        line_lon += [lon, t_lon, None]
    fig.add_trace(go.Scattergeo(lat=line_lat, lon=line_lon, mode="lines",
                                line=dict(width=1, color="#9cf"), name="Lines of sight",
                                hoverinfo="skip"))
    fig.add_trace(go.Scattergeo(
        lat=[a[1] for a in anchors], lon=[a[2] for a in anchors], mode="markers+text",
        text=[a[0] for a in anchors], textposition="bottom center",
        marker=dict(size=8, color="#4af", symbol="diamond"), name="Known positions",
        hovertemplate="%{text}<br>lat %{lat:.3f}°<br>lon %{lon:.3f}°<extra></extra>",
    ))
    fig.add_trace(go.Scattergeo(
        lat=[t_lat], lon=[t_lon], mode="markers+text", text=[t_name], textposition="top center",
        marker=dict(size=12, color="red", symbol="circle-open", line=dict(width=3)),
        name=f"Truth: {t_name}",
        hovertemplate=f"lat {t_lat:.5f}°<br>lon {t_lon:.5f}°<br>alt {t_alt:.3f} km<extra></extra>",
    ))
    for (label, lat, lon, alt, err), color in zip(estimates, ["yellow", "lime", "magenta"]):
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers", marker=dict(size=7, color=color, symbol="x"),
            name=f"Estimate ({label}): {err:.1f} m",
            hovertemplate=(f"{label}<br>lat {lat:.5f}°<br>lon {lon:.5f}°<br>alt {alt:.3f} km"
                           f"<br>error {err:.1f} m<extra></extra>"),
        ))
    style_globe(fig, t_lat, t_lon)
    fig.update_layout(title=title)
    return fig
