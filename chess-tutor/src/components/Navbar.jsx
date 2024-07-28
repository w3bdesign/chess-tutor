import React from "react";
import { Link } from "react-router-dom";

const Navbar = () => {
  return (
    <nav className="bg-slate-200 rounded shadow p-2 mb-4">
      <ul className="flex space-x-2 p-2">
        <li className="group p-2 rounded hover:bg-slate-400 transition duration-300 ease-in-out hover:text-gray-100">
          <Link
            to="/"
            className="text-gray-900 group-hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Analysis
          </Link>
        </li>
        <li className="group p-2 rounded hover:bg-slate-400 transition duration-300 ease-in-out hover:text-gray-100">
          <Link
            to="/puzzles"
            className="text-gray-900 group-hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Puzzles
          </Link>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar;
