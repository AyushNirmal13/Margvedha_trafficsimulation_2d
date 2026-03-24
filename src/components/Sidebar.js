import React from "react";
import { Link } from "react-router-dom";
import { FaTachometerAlt, FaMapMarkerAlt, FaCamera, FaBell, FaChartBar, FaCog } from "react-icons/fa";
import "./Sidebar.css";
import { color } from "chart.js/helpers";

const Sidebar = () => {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <img src="../logo.svg" alt="Marg Vedha Logo" className="sidebar-logo" />
      </div>
      <ul>
        <li>
          <Link to="/dashboard" className="sidebar-link">
            <FaTachometerAlt className="sidebar-icon" /> Dashboard
          </Link>
        </li>
        <li>
          <Link to="/camera-feeds" className="sidebar-link">
            <FaCamera className="sidebar-icon" /> Camera Feeds
          </Link>
        </li>
        <li>
          <Link to="/2d-map" className="sidebar-link">
            <FaMapMarkerAlt className="sidebar-icon" /> 2D Traffic Map
          </Link>
        </li>
        <li>
          <Link to="/traffic-alerts" className="sidebar-link">
            <FaBell className="sidebar-icon" /> Traffic Alerts
          </Link>
        </li>
        <li>
          <Link to="/reports" className="sidebar-link">
            <FaChartBar className="sidebar-icon" /> Reports
          </Link>
        </li>
        <li>
          <Link to="/settings" className="sidebar-link">
            <FaCog className="sidebar-icon" /> Settings
          </Link>
        </li>
      </ul>
      <div>
        <h1 className="contact-detail"><a href="https://github.com/Aditya948351/MargVedhaMain" target="_blank">Github</a></h1>
      </div>
    </div>
  );
};

export default Sidebar;
