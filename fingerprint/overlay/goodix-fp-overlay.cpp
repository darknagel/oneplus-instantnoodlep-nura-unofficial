// SPDX-License-Identifier: LGPL-2.1-or-later
// Light the in-display fingerprint sensor of the OnePlus 8 Pro under a Wayland
// compositor. The optical sensor only sees a finger that the screen lights up.
// fprintd announces "finger-needed" and "finger-present" on the system bus;
// while a finger is needed this draws a ring over the sensor, while one is
// present a white disk under it. The window sits on the layer-shell overlay
// layer, takes no input (touches go to the apps; the libfprint driver reads
// the touchscreen itself) and stays mapped but fully transparent while fprintd
// needs nothing (a re-shown window would be a new surface). The surface is
// marked with kde_lockscreen_overlay_v1, so KWin also shows it over the lock
// screen, where fingerprint unlock happens.
#include <QDBusConnection>
#include <QGuiApplication>
#include <QPainter>
#include <QRasterWindow>
#include <QScreen>
#include <QSurfaceFormat>
#include <LayerShellQt/Window>
#include <QWaylandClientExtensionTemplate>
#include <QtWaylandClient/private/qwaylandwindow_p.h>

#include "qwayland-kde-lockscreen-overlay-v1.h"

static bool debugEnabled()
{
    static const bool on = qEnvironmentVariableIsSet("GOODIX_FP_OVERLAY_DEBUG");
    return on;
}

class LockscreenOverlay : public QWaylandClientExtensionTemplate<LockscreenOverlay>,
                          public QtWayland::kde_lockscreen_overlay_v1
{
public:
    LockscreenOverlay()
        : QWaylandClientExtensionTemplate<LockscreenOverlay>(1)
    {
        initialize();
    }
    ~LockscreenOverlay() override
    {
        if (isActive())
            destroy();
    }
};

// OnePlus 8 Pro (1440x3168): sensor centre and radii as fractions of the width
static constexpr double kCenterX = 720.0 / 1440.0;
static constexpr double kCenterY = 2547.0 / 3168.0;
static constexpr double kDiskR = 190.0 / 1440.0;
static constexpr double kRingR = 202.0 / 1440.0;
static constexpr double kRingW = 14.0 / 1440.0;

static const char *kDeviceIface = "net.reactivated.Fprint.Device";

class Overlay : public QRasterWindow
{
    Q_OBJECT
public:
    Overlay()
    {
        QSurfaceFormat fmt = format();
        fmt.setAlphaBufferSize(8);
        setFormat(fmt);
        setFlag(Qt::WindowTransparentForInput);
        setFlag(Qt::FramelessWindowHint);
        if (auto *ls = LayerShellQt::Window::get(this)) {
            ls->setLayer(LayerShellQt::Window::LayerOverlay);
            ls->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop |
                LayerShellQt::Window::AnchorBottom | LayerShellQt::Window::AnchorLeft |
                LayerShellQt::Window::AnchorRight));
            ls->setExclusiveZone(-1);
            ls->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
            ls->setScope(QStringLiteral("goodix-fp-overlay"));
        }
        if (QScreen *s = QGuiApplication::primaryScreen())
            resize(s->size());
    }

    // KWin applies allow() only to a surface that already has a window (the
    // layer surface exists) and is not mapped yet (no buffer); right after
    // show() is exactly that, the first buffer follows the configure event
    void allowOverLockscreen()
    {
        auto *ww = dynamic_cast<QtWaylandClient::QWaylandWindow *>(handle());
        const bool active = m_lockscreen.isActive();
        if (active && ww && ww->wlSurface())
            m_lockscreen.allow(ww->wlSurface());
        if (debugEnabled())
            qInfo("lockscreen overlay: %s", active ? "allowed" : "interface not offered");
    }

    void watch(const QString &path)
    {
        QDBusConnection bus = QDBusConnection::systemBus();
        // fprintd is D-Bus activated and exits when idle, so match on the
        // well-known name's object path from any sender
        const bool ok = bus.connect(QString(), path,
                    QStringLiteral("org.freedesktop.DBus.Properties"),
                    QStringLiteral("PropertiesChanged"), this,
                    SLOT(propertiesChanged(QString, QVariantMap, QStringList)));
        if (debugEnabled())
            qInfo("system bus %s, watching %s: %s", bus.isConnected() ? "up" : "DOWN",
                  qPrintable(path), ok ? "ok" : "FAILED");
    }

public Q_SLOTS:
    void propertiesChanged(const QString &iface, const QVariantMap &changed, const QStringList &)
    {
        if (iface != QLatin1String(kDeviceIface))
            return;
        if (changed.contains(QStringLiteral("finger-needed")))
            m_needed = changed.value(QStringLiteral("finger-needed")).toBool();
        if (changed.contains(QStringLiteral("finger-present")))
            m_present = changed.value(QStringLiteral("finger-present")).toBool();
        if (debugEnabled())
            qInfo("finger-needed=%d finger-present=%d", m_needed, m_present);
        update();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setCompositionMode(QPainter::CompositionMode_Source);
        p.fillRect(QRect(0, 0, width(), height()), Qt::transparent);
        p.setCompositionMode(QPainter::CompositionMode_SourceOver);
        p.setRenderHint(QPainter::Antialiasing);
        const double w = width();
        const QPointF c(kCenterX * w, kCenterY * height());
        if (m_present) {
            p.setPen(Qt::NoPen);
            p.setBrush(Qt::white);
            p.drawEllipse(c, kDiskR * w, kDiskR * w);
        } else if (m_needed) {
            QPen pen(QColor(0x00, 0xa0, 0xff));
            pen.setWidthF(kRingW * w);
            p.setPen(pen);
            p.setBrush(Qt::NoBrush);
            p.drawEllipse(c, kRingR * w, kRingR * w);
        }
    }

private:
    LockscreenOverlay m_lockscreen;
    bool m_needed = false;
    bool m_present = false;
};

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("goodix-fp-overlay"));
    app.setDesktopFileName(QStringLiteral("goodix-fp-overlay"));
    Overlay overlay;
    // fprintd numbers its devices from 0; this phone has one reader
    overlay.watch(QStringLiteral("/net/reactivated/Fprint/Device/0"));
    overlay.show();
    overlay.allowOverLockscreen();
    return app.exec();
}

#include "goodix-fp-overlay.moc"
