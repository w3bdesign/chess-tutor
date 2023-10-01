import { useState } from "react";

import "./App.css";

function App() {
  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-2">Chess Tutor</h1>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded p-4 w-full min-w-[25rem] min-h-[20rem]">Test</div>
      </div>
    </>
  );
}

export default App;
