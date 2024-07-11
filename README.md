# Chess Tutor

![Chess Tutor](https://github.com/w3bdesign/chess-tutor/assets/45217974/25ad0cb5-b21a-4022-8ee0-ea7a79fc68cf)

Chess Tutor is an interactive web application that helps users improve their chess skills by providing real-time move analysis and suggestions using the Stockfish chess engine.

## Features

- Interactive chessboard with drag-and-drop functionality
- Real-time move evaluation using Stockfish API
- Best move suggestions with visual arrows
- Detailed move history with Unicode chess piece symbols
- Responsive design for various screen sizes

## Technologies Used

- React
- [Chessboard2](https://github.com/oakmac/chessboard2) for the chessboard UI
- [chess.js](https://github.com/jhlywa/chess.js) for chess move validation and game state
- [Stockfish Online API](https://stockfish.online/) for move evaluation
- [TanStack Query](https://tanstack.com/query/latest) for efficient data fetching and caching
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

4. Start the development server:
   ```
   npm run dev
   ```
   or
   ```
   yarn dev
   ```

5. Open your browser and visit `http://localhost:5173` (or the port specified in your console).

## Usage

1. The chessboard is set up in the starting position.
2. Drag and drop pieces to make moves.
3. The application will display the current evaluation and the best move suggestion.
4. The move history is updated after each move, showing Unicode chess piece symbols.
5. Invalid moves will display warning messages to guide the user.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- [Stockfish Online](https://stockfish.online/) for providing the chess engine API
- [Chris Oakman](https://github.com/oakmac) for the Chessboard2 library
- [Jeff Hlywa](https://github.com/jhlywa) for the chess.js library

## Contact

Your Name - [@your_twitter](https://twitter.com/your_twitter) - email@example.com

Project Link: [https://github.com/your-username/chess-tutor](https://github.com/your-username/chess-tutor)