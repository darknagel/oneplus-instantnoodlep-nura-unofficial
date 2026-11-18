// SPDX-License-Identifier: LGPL-2.1-or-later
// Light the in-display fingerprint sensor of the OnePlus 8 Pro under a Wayland
// compositor. The optical sensor only sees a finger that the screen lights up.
// fprintd announces "finger-needed" and "finger-present" on the system bus;
// while a finger is needed this draws a Breeze-style ring with the fingerprint
// icon over the sensor, while one is present a plain white disk under it. The window sits on the layer-shell overlay
// layer, takes no input (touches go to the apps; the libfprint driver reads
// the touchscreen itself) and stays mapped but fully transparent while fprintd
// needs nothing (a re-shown window would be a new surface). The surface is
// marked with kde_lockscreen_overlay_v1, so KWin also shows it over the lock
// screen, where fingerprint unlock happens. While a finger lies on the sensor
// the backlight goes to full brightness (through logind, as the session user),
// as Android does; the sensor misses the finger in a dim picture.
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusInterface>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QDir>
#include <QFile>
#include <QPainterPath>
#include <QPaintEvent>
#include <QRadialGradient>
#include <QPolygonF>
#include <algorithm>
#include <cmath>
#include <QtMath>
#include <QGuiApplication>
#include <QIcon>
#include <QPalette>
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

// OnePlus 8 Pro panel (1440x3168, portrait): sensor centre as fractions of the
// panel, radii as fractions of its short side
static constexpr double kCenterX = 720.0 / 1440.0;
static constexpr double kCenterY = 2547.0 / 3168.0;
static constexpr double kDiskR = 190.0 / 1440.0;
static constexpr double kRingR = 202.0 / 1440.0;
static constexpr double kRingW = 14.0 / 1440.0;

// Full backlight while a finger is on the sensor, the previous value after
class Backlight
{
public:
    Backlight()
    {
        const QStringList devs = QDir(QStringLiteral("/sys/class/backlight"))
                .entryList(QDir::Dirs | QDir::NoDotAndDotDot);
        if (!devs.isEmpty())
            m_name = devs.first();
    }
    ~Backlight() { restore(); }

    void boost()
    {
        if (m_name.isEmpty() || m_saved >= 0)
            return;
        const int cur = read(QStringLiteral("brightness"));
        const int max = read(QStringLiteral("max_brightness"));
        if (cur < 0 || max <= 0 || cur >= max)
            return;
        m_saved = cur;
        set(max);
    }

    void restore()
    {
        if (m_saved < 0)
            return;
        set(m_saved);
        m_saved = -1;
    }

private:
    int read(const QString &file) const
    {
        QFile f(QStringLiteral("/sys/class/backlight/%1/%2").arg(m_name, file));
        if (!f.open(QIODevice::ReadOnly))
            return -1;
        bool ok = false;
        const int v = f.readAll().trimmed().toInt(&ok);
        return ok ? v : -1;
    }

    void set(int value)
    {
        // "auto" is the caller's session, or the user's display session for a
        // process outside one (the autostart unit runs in the user manager)
        QDBusInterface session(QStringLiteral("org.freedesktop.login1"),
                QStringLiteral("/org/freedesktop/login1/session/auto"),
                QStringLiteral("org.freedesktop.login1.Session"),
                QDBusConnection::systemBus());
        session.asyncCall(QStringLiteral("SetBrightness"), QStringLiteral("backlight"), m_name,
                          quint32(value));
        if (debugEnabled())
            qInfo("backlight %s -> %d", qPrintable(m_name), value);
    }

    QString m_name;
    int m_saved = -1;
};

static const char *kService = "net.reactivated.Fprint";
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
            // a small window over the sensor, placed by its margins: a full
            // screen one costs a full-screen buffer copy for every frame
            ls->setAnchors(LayerShellQt::Window::Anchors(LayerShellQt::Window::AnchorTop |
                LayerShellQt::Window::AnchorLeft));
            ls->setExclusiveZone(-1);
            ls->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
            ls->setScope(QStringLiteral("goodix-fp-overlay"));
        }
        if (QScreen *s = QGuiApplication::primaryScreen()) {
            setScreen(s);
            connect(s, &QScreen::orientationChanged, this, &Overlay::place);
            connect(s, &QScreen::geometryChanged, this, &Overlay::place);
        }
        place();
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

        // fprintd gone (idle exit, crash): nothing is waiting any more
        m_service = new QDBusServiceWatcher(QString::fromLatin1(kService), bus,
                QDBusServiceWatcher::WatchForUnregistration, this);
        connect(m_service, &QDBusServiceWatcher::serviceUnregistered, this,
                [this] { apply(false, false); });

        // started while fprintd already waits (session start, restart after a
        // KWin crash on the lock screen): fetch the current state, without
        // activating fprintd
        if (!bus.interface()->isServiceRegistered(QString::fromLatin1(kService)))
            return;
        QDBusMessage get = QDBusMessage::createMethodCall(QString::fromLatin1(kService), path,
                QStringLiteral("org.freedesktop.DBus.Properties"), QStringLiteral("GetAll"));
        get << QString::fromLatin1(kDeviceIface);
        auto *call = new QDBusPendingCallWatcher(bus.asyncCall(get), this);
        connect(call, &QDBusPendingCallWatcher::finished, this, [this](QDBusPendingCallWatcher *w) {
            QDBusPendingReply<QVariantMap> reply = *w;
            if (!reply.isError())
                propertiesChanged(QString::fromLatin1(kDeviceIface), reply.value(), {});
            w->deleteLater();
        });
    }

public Q_SLOTS:
    void propertiesChanged(const QString &iface, const QVariantMap &changed, const QStringList &)
    {
        if (iface != QLatin1String(kDeviceIface))
            return;
        apply(changed.value(QStringLiteral("finger-needed"), m_needed).toBool(),
              changed.value(QStringLiteral("finger-present"), m_present).toBool());
    }

private:
    void apply(bool needed, bool present)
    {
        m_needed = needed;
        m_present = present;
        if (debugEnabled())
            qInfo("finger-needed=%d finger-present=%d", m_needed, m_present);
        if (m_present)
            m_backlight.boost();
        else
            m_backlight.restore();
        update();
    }

protected:
    bool event(QEvent *e) override
    {
        if (e->type() == QEvent::ApplicationPaletteChange
            || e->type() == QEvent::ThemeChange) {
            m_map = QImage();
            update();
        }
        return QRasterWindow::event(e);
    }

    void paintEvent(QPaintEvent *e) override
    {
        QPainter p(this);
        p.setCompositionMode(QPainter::CompositionMode_Source);
        p.fillRect(e->rect(), Qt::transparent);
        p.setCompositionMode(QPainter::CompositionMode_SourceOver);
        p.setRenderHint(QPainter::Antialiasing);
        const double unit = m_unit;
        const QPointF c = m_local;
        if (m_present) {
            // the sensor images the finger in this light: plain white, no effects
            p.setPen(Qt::NoPen);
            p.setBrush(Qt::white);
            p.drawEllipse(c, kDiskR * unit, kDiskR * unit);
        } else if (m_needed) {
            if (m_map.isNull() || m_map.devicePixelRatio() != devicePixelRatio())
                m_map = renderPlasma(size(), devicePixelRatio(), m_local, kRingR * unit,
                                     kRingW * unit);
            p.drawImage(0, 0, m_map);
        }
    }

private:
    // Breeze look: a translucent round plate in the colour scheme's window
    // colour with a soft shadow, a ring in the accent colour with a faint
    // focus glow, and the theme's fingerprint icon in the middle. Follows the
    // colour scheme (light/dark) and the accent colour. Drawn once, static.
    static QImage renderPlasma(const QSize &size, qreal dpr, const QPointF &c, double r, double w)
    {
        QImage img(size * dpr, QImage::Format_ARGB32_Premultiplied);
        img.setDevicePixelRatio(dpr);
        img.fill(Qt::transparent);
        QPainter p(&img);
        p.setRenderHint(QPainter::Antialiasing);
        p.setRenderHint(QPainter::SmoothPixmapTransform);

        const QPalette pal = QGuiApplication::palette();
        const QColor accent = pal.color(QPalette::Highlight);
        QColor plate = pal.color(QPalette::Window);
        QColor text = pal.color(QPalette::WindowText);
        const double rp = r * 1.32;

        // shadow like a Plasma popup
        QRadialGradient shadow(c + QPointF(0, r * 0.04), rp * 1.12);
        shadow.setColorAt(0.86, QColor(0, 0, 0, 70));
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0));
        p.setPen(Qt::NoPen);
        p.setBrush(shadow);
        p.drawEllipse(c + QPointF(0, r * 0.04), rp * 1.12, rp * 1.12);

        // plate with a hairline frame
        plate.setAlpha(225);
        p.setBrush(plate);
        QColor frame = text;
        frame.setAlpha(40);
        p.setPen(QPen(frame, qMax(1.0, r * 0.012)));
        p.drawEllipse(c, rp, rp);

        // accent ring with a focus glow
        QColor glow = accent;
        glow.setAlpha(70);
        p.setBrush(Qt::NoBrush);
        p.setPen(QPen(glow, w * 2.6));
        p.drawEllipse(c, r, r);
        p.setPen(QPen(accent, w));
        p.drawEllipse(c, r, r);

        // the theme's fingerprint icon, recoloured for the scheme by KDE's
        // icon engine; a drawn fallback if the theme has none
        const double is = r * 0.95;
        const QIcon icon = QIcon::fromTheme(QStringLiteral("fingerprint-symbolic"),
                                            QIcon::fromTheme(QStringLiteral("fingerprint")));
        if (!icon.isNull()) {
            const QPixmap pm = icon.pixmap(QSize(qCeil(is), qCeil(is)), dpr);
            p.setOpacity(0.85);
            p.drawPixmap(QRectF(c.x() - is / 2, c.y() - is / 2, is, is), pm, pm.rect());
            p.setOpacity(1.0);
        } else {
            text.setAlpha(200);
            p.setPen(QPen(text, r * 0.05, Qt::SolidLine, Qt::RoundCap));
            for (int k = 1; k <= 4; ++k) {
                const double rr = is * 0.12 * k;
                p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), 200 * 16, 140 * 16);
            }
        }
        return img;
    }

    // The sensor sits at a fixed place of the panel; with the output rotated
    // it is somewhere else on the screen. Size and place the window around it.
    void place()
    {
        QScreen *s = screen();
        if (!s)
            return;
        const double w = s->size().width(), h = s->size().height();
        const int angle = s->angleBetween(Qt::PortraitOrientation, s->orientation());
        QPointF c;
        switch (angle) {
        case 90:
            c = QPointF((1.0 - kCenterY) * w, kCenterX * h);
            break;
        case 180:
            c = QPointF((1.0 - kCenterX) * w, (1.0 - kCenterY) * h);
            break;
        case 270:
            c = QPointF(kCenterY * w, (1.0 - kCenterX) * h);
            break;
        default:
            c = QPointF(kCenterX * w, kCenterY * h);
        }
        m_unit = qMin(w, h);
        // room for the plate and its shadow around the sensor
        const double r = kRingR * m_unit;
        const int ww = qCeil(r * 3.2), wh = ww;
        m_local = QPointF(ww / 2.0, wh / 2.0);
        resize(ww, wh);
        if (auto *ls = LayerShellQt::Window::get(this))
            ls->setMargins(QMargins(qRound(c.x() - m_local.x()), qRound(c.y() - m_local.y()), 0, 0));
        if (debugEnabled())
            qInfo("angle %d: %dx%d window, sensor at %.0f,%.0f", angle, ww, wh, c.x(), c.y());
        m_map = QImage();
        update();
    }

    Backlight m_backlight;
    LockscreenOverlay m_lockscreen;
    QDBusServiceWatcher *m_service = nullptr;
    QImage m_map;
    QPointF m_local;
    double m_unit = 1;
    bool m_needed = false;
    bool m_present = false;
};

int main(int argc, char **argv)
{
    // Plasma lets Qt reconnect to a restarted KWin, but the new surface would
    // miss the lock screen mark; exit instead and let systemd (restart.conf)
    // start a fresh process
    qunsetenv("QT_WAYLAND_RECONNECT");
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
