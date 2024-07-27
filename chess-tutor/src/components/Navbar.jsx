import React from "react";

const Navbar = () => {
  return (
    <nav className=" bg-slate-200 rounded shadow p-2 mb-4">
      <ul className="flex space-x-2 p-2 ">
        <li className="group p-2 rounded hover:bg-slate-400 transition duration-300 ease-in-out hover:text-gray-100">
          <a
            href="#analysis"
            className="text-gray-900 group-hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Analysis
          </a>
        </li>
        <li className="hidden group p-2 rounded hover:bg-slate-400 transition duration-300 ease-in-out hover:text-gray-100">
          <a
            href="#puzzles"
            className="text-gray-900 group-hover:text-gray-100 transition duration-300 ease-in-out"
          >
            Puzzles
          </a>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar;
