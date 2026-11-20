import { Cartesian3, Color, EllipsoidTerrainProvider, Viewer } from "cesium";

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
  viewer.camera.setView({ destination: Cartesian3.fromDegrees(15, 20, 22_000_000) });
  return viewer;
}
