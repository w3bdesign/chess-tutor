import React from "react";

const Navbar = () => {
  return (
    <nav className="bg-gray-800 p-2 mb-4">
      <ul className="flex space-x-2 p-2 ">
        <li className="border border-white p-2 rounded bg-gray-600 shadow">
          <a href="#analysis" className="text-white hover:text-gray-300 transition duration-300 ease-in-out">
            Analysis
          </a>
        </li>
        <li className="border border-white p-2 rounded bg-gray-600 shadow border hidden">
          <a href="#puzzles" className="text-white hover:text-gray-300 transition duration-300 ease-in-out">
            Puzzles
          </a>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar;
