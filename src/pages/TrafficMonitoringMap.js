import React, { useState, useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import "./TrafficMonitoringMap.css";

// Generate 80 cameras in Nashik area
const generateCameras = () => {
  const cams = [];
  for (let i = 1; i <= 80; i++) {
    cams.push({
      id: `cam${i.toString().padStart(2, "0")}`,
      name: `Camera ${i}`,
      lat: 19.98 + Math.random() * 0.04,
      lon: 73.74 + Math.random() * 0.06,
    });
  }
  return cams;
};

// We'll create a box format point using Leaflet DivIcon
const createTrafficIcon = (car, bike, bus) => {
  const html = `
    <div style="
      background-color: white;
      border: 2px solid #333;
      border-radius: 4px;
      padding: 2px;
      display: flex;
      flex-direction: column;
      font-size: 11px;
      line-height: 1.2;
      width: 45px;
      text-align: center;
      box-shadow: 0 0 5px rgba(0,0,0,0.5);
      font-weight: bold;
    ">
      <div style="background-color: #ff4d4d; color: white; border-radius: 2px; margin-bottom: 2px;">🚗 ${car}</div>
      <div style="background-color: #4da6ff; color: white; border-radius: 2px; margin-bottom: 2px;">🏍️ ${bike}</div>
      <div style="background-color: #4dff4d; color: black; border-radius: 2px;">🚌 ${bus}</div>
    </div>
  `;

  return L.divIcon({
    html,
    className: "custom-traffic-icon",
    iconSize: [45, 50],
    iconAnchor: [22, 25],
  });
};

const TrafficMonitoringMap = () => {
  const cameras = useMemo(() => generateCameras(), []);
  const [trafficData, setTrafficData] = useState({});
  const mapRef = useRef(null);

  useEffect(() => {
    // Simulate real-time traffic updates
    const updateTraffic = () => {
      const newData = {};
      cameras.forEach(cam => {
        newData[cam.id] = {
          car: Math.floor(Math.random() * 50),
          bike: Math.floor(Math.random() * 80),
          bus: Math.floor(Math.random() * 15),
        };
      });
      setTrafficData(newData);
    };

    updateTraffic(); // Initial load
    const interval = setInterval(updateTraffic, 3000); // Update every 3 seconds
    return () => clearInterval(interval);
  }, [cameras]);

  // Handle camera selection from the dropdown
  const handleCameraSelect = (e) => {
    const camId = e.target.value;
    if (!camId) return;

    const selectedCam = cameras.find(c => c.id === camId);
    if (selectedCam && mapRef.current) {
      // Fix any internal coordinate offsets before moving
      mapRef.current.invalidateSize();
      // Use the cool flyTo animation per user request
      mapRef.current.flyTo([selectedCam.lat, selectedCam.lon], 16, {
        duration: 1.5 // Smooth animation
      });
    }
  };

  return (
    <div className="traffic-map-container">
      <h2 style={{ marginBottom: "20px", color: "#333" }}>Live Nashik Traffic Feeds</h2>
      
      <div className="camera-controls">
        <label htmlFor="camera-select">Search & Select Camera:</label>
        <select id="camera-select" className="camera-select" onChange={handleCameraSelect} defaultValue="">
          <option value="" disabled>-- View All Cameras --</option>
          {cameras.map(cam => (
            <option key={cam.id} value={cam.id}>
              {cam.id.toUpperCase()} - {cam.name}
            </option>
          ))}
        </select>
      </div>

      <MapContainer 
        center={[20.0059, 73.7799]} 
        zoom={13} 
        ref={mapRef}
        style={{ height: "650px", width: "100%", borderRadius: "10px", border: "2px solid #ddd", zIndex: 0 }}
      >
        <TileLayer 
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" 
          attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
        />
        
        {cameras.map((cam) => {
          const data = trafficData[cam.id] || { car: 0, bike: 0, bus: 0 };
          return (
            <Marker 
              key={cam.id} 
              position={[cam.lat, cam.lon]} 
              icon={createTrafficIcon(data.car, data.bike, data.bus)}
            >
              <Popup>
                <div style={{ textAlign: "center" }}>
                  <strong>{cam.name} ({cam.id})</strong><br/>
                  <small>Lat: {cam.lat.toFixed(4)}, Lon: {cam.lon.toFixed(4)}</small><br/><br/>
                  <span style={{ color: "#e60000", fontWeight: "bold" }}>🚗 Cars: {data.car}</span><br/>
                  <span style={{ color: "#0066cc", fontWeight: "bold" }}>🏍️ Bikes: {data.bike}</span><br/>
                  <span style={{ color: "#00b300", fontWeight: "bold" }}>🚌 Buses: {data.bus}</span>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
};

export default TrafficMonitoringMap;
