import React from "react";
import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Alerts from "./pages/Alerts";
import LiveFeed from "./pages/LiveFeed";
import MapLocation from "./pages/MapLocation";
import CameraFeeds from "./pages/CameraFeeds";
import EmergencyAlerts from "./pages/EmergencyAlerts";
import TrafficCounting from "./pages/TrafficCounting";
import BusRouteOptimization from "./pages/BusRouteOptimization";
import BlockChainTicketing from "./pages/BlockChainTicketing";
import AutoFareAdjustments from "./pages/AutoFareAdjustments";
import Home from "./pages/Home";
import TrafficMonitoringMap from "./pages/TrafficMonitoringMap";
function App() {
  const isAuthenticated = true; // <--- Bypass login by hardcoding to true

  const handleLogout = () => {
    // Optional: No real logout now, since we always authenticate
    console.log("Logout disabled in bypass mode.");
  };

  return (
    <div className="d-flex">
      {isAuthenticated && <Sidebar />}

      <div className="content-area w-100">
        <Routes>
          {/* Redirect root (/) to /dashboard */}
          <Route path="/" element={<Dashboard onLogout={handleLogout} />} />

          {/* All other routes are accessible since we are always "logged in" */}
          <Route path="/dashboard" element={<Dashboard onLogout={handleLogout} />} />
          <Route path="/2d-map" element={<TrafficMonitoringMap />} />
          <Route path="/google-map" element={<MapLocation />} />
          <Route path="/camera-feeds" element={<CameraFeeds />} />
          <Route path="/traffic-alerts" element={<Alerts />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/live-feed" element={<LiveFeed />} />
          <Route path="/EmergencyAlerts" element={<EmergencyAlerts />} />
          <Route path="/TrafficCounting" element={<TrafficCounting />} />
          <Route path="/BusRouteOptimization" element={<BusRouteOptimization />} />
          <Route path="/BlockChainTicketing" element={<BlockChainTicketing />} />
          <Route path="/AutoFareAdjustments" element={<AutoFareAdjustments />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
