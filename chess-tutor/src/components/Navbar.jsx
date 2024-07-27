import React from 'react';

const Navbar = () => {
  return (
    <nav className="bg-gray-800 p-4">
      <ul className="flex space-x-4">
        <li>
          <a href="#analysis" className="text-white hover:text-gray-400">Analysis</a>
        </li>
        <li className="hidden">
          <a href="#puzzles" className="text-white hover:text-gray-400">Puzzles</a>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar;
