import { Cartesian3, Color, EllipsoidTerrainProvider, PerspectiveFrustum, Viewer } from "cesium";

/** Local ellipsoid and bundled assets: no ion token or remote tile service. */
export function createViewer(container: string): Viewer {
  const viewer = new Viewer(container, {
    animation: false,
    timeline: false,
    geocoder: false,
    homeButton: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    baseLayer: false,
    terrainProvider: new EllipsoidTerrainProvider(),
    requestRenderMode: true,
    maximumRenderTimeChange: Infinity,
  });
  viewer.scene.globe.baseColor = Color.fromCssColorString("#283748");
  viewer.scene.globe.enableLighting = false;
  viewer.camera.setView({ destination: Cartesian3.fromDegrees(15, 0, 22_000_000) });
  // Resize the actual canvas when its available layout space changes, including
  // when request-render mode or a background tab suspends the animation loop.
  const fieldOfView = (viewer.camera.frustum as PerspectiveFrustum).fov;
  const resize = new ResizeObserver(() => {
    viewer.resize();
    const aspect = viewer.canvas.clientWidth / viewer.canvas.clientHeight;
    const frustum = viewer.camera.frustum;
    if (fieldOfView !== undefined && Number.isFinite(aspect) && aspect > 0 && frustum instanceof PerspectiveFrustum) {
      // Cesium defines fov along the longer axis. Preserve the original angle
      // along the shorter axis so the global view fits tall and wide canvases,
      // without moving the camera or changing its geographic target.
      frustum.fov = 2 * Math.atan(Math.tan(fieldOfView / 2) * Math.max(aspect, 1 / aspect));
    }
    viewer.scene.requestRender();
    viewer.render();
  });
  resize.observe(viewer.container);
  const destroy = viewer.destroy.bind(viewer);
  viewer.destroy = () => { resize.disconnect(); return destroy(); };
  return viewer;
}
