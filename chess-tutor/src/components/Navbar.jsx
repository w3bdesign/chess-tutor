import React from "react";

const Navbar = () => {
  return (
    <nav className=" bg-slate-300 rounded shadow p-2 mb-4">
      <ul className="flex space-x-2 p-2">
        <li className="group border border-gray-600 p-2 rounded bg-gray-200 shadow hover:bg-gray-500 transition duration-300 ease-in-out hover:text-gray-100">
          <a
            href="#analysis"
            className="text-gray-900 group-hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Analysis
          </a>
        </li>
        <li className="border border-gray-600 p-2 rounded bg-gray-500 shadow border hidden">
          <a
            href="#puzzles"
            className="text-gray-900 hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Puzzles
          </a>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar;
