# Chess Tutor

![image](https://github.com/user-attachments/assets/492951bb-6509-4ff9-963c-db4a5b75c437)

Chess Tutor is an interactive web application that helps users improve their chess skills by providing real-time move analysis, suggestions using the Stockfish chess engine, and challenging chess puzzles.

## Features

- Interactive chessboard with drag-and-drop functionality
- Real-time move evaluation using Stockfish API
- Best move suggestions with visual arrows
- Detailed move history with Unicode chess piece symbols
- Chess puzzles for skill improvement
- Responsive design for various screen sizes
- Zustand for centralized state management
- Fallback to Chess API if Stockfish evaluation takes longer than 5 seconds

## Technologies Used

- React
- [Chessboard2](https://github.com/oakmac/chessboard2) for the chessboard UI
- [chess.js](https://github.com/jhlywa/chess.js) for chess move validation and game state
- [Stockfish Online API](https://stockfish.online/) for move evaluation
- [Chess API](https://chess-api.com/) as a fallback provider
- [Chess Puzzles API](https://rapidapi.com/KeeghanM/api/chess-puzzles/) for puzzle generation
- [TanStack Query](https://tanstack.com/query/latest) for efficient data fetching and caching
- [Zustand](https://docs.pmnd.rs/zustand/getting-started/introduction) for centralized state management
- Tailwind CSS for styling

## Getting Started

### Prerequisites

- Node.js (version 18 or higher)
- npm or yarn

### Installation

1. Clone the repository:

   ```
   git clone https://github.com/your-username/chess-tutor.git
   ```

2. Navigate to the project directory:

   ```
   cd chess-tutor
   ```

3. Install dependencies:

   ```
   npm install
   ```

   or

   ```
   yarn install
   ```

4. Create a `.env` file in the root directory and add your RapidAPI key:

   ```
   VITE_RAPID_API_KEY=your_rapidapi_key_here
   ```

5. Start the development server:

   ```
   npm run dev
   ```

   or

   ```
   yarn dev
   ```

6. Open your browser and visit `http://localhost:5173` (or the port specified in your console).

## Usage

### Chess Analysis

1. The chessboard is set up in the starting position.
2. Drag and drop pieces to make moves.
3. The application will display the current evaluation and the best move suggestion.
4. The move history is updated after each move, showing Unicode chess piece symbols.
5. Invalid moves will display warning messages to guide the user.

### Chess Puzzles

1. Navigate to the Puzzles section of the application.
2. A chess puzzle will be presented with a specific position and goal.
3. Try to find the best move(s) to solve the puzzle.
4. Use the hint feature if you're stuck.
5. After solving or failing a puzzle, a new one will be loaded automatically.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
