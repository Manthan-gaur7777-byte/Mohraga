import math
from collections import Counter, defaultdict, deque

import pygame

WIDTH, HEIGHT = 1000, 700
ARENA = pygame.Rect(32, 92, WIDTH - 64, HEIGHT - 124)
BG = (13, 18, 28)
PANEL = (21, 29, 43)
TEXT = (222, 231, 242)
MUTED = (139, 155, 177)
BLUE = (76, 168, 255)
RED = (244, 92, 104)
GOLD = (247, 190, 76)
GREEN = (86, 210, 143)
ATTACKS = ("jab", "slash", "heavy")
POWER_CHOICES = {
    pygame.K_1: ("med_kit", "MED KIT", "+35 health"),
    pygame.K_2: ("overdrive", "OVERDRIVE", "+35% attack damage"),
    pygame.K_3: ("phase_boots", "PHASE BOOTS", "+speed and faster dodges"),
}


def clamp(value, low, high):
    return max(low, min(high, value))


class PatternLearner:
    def __init__(self):
        self.transitions = defaultdict(Counter)
        self.global_counts = Counter()
        self.recent_attacks = deque(maxlen=8)
        self.last_attack = None
        self.total_attacks = 0

    def observe(self, attack):
        for counts in self.transitions.values():
            for name in list(counts):
                counts[name] *= 0.84
                if counts[name] < 0.05:
                    del counts[name]
        for name in list(self.global_counts):
            self.global_counts[name] *= 0.93
            if self.global_counts[name] < 0.05:
                del self.global_counts[name]
        if self.last_attack is not None:
            self.transitions[self.last_attack][attack] += 4.0
        self.global_counts[attack] += 2.0
        self.recent_attacks.append(attack)
        self.last_attack = attack
        self.total_attacks += 1

    def _scores(self):
        scores = Counter(self.transitions.get(self.last_attack, self.global_counts))
        for index, attack in enumerate(reversed(self.recent_attacks), start=1):
            scores[attack] += max(0.35, 2.0 - index * 0.16)
        return scores

    def predict(self):
        counts = self._scores()
        if not counts:
            return "slash", 0.0
        total = sum(counts.values())
        choice, value = max(counts.items(), key=lambda item: item[1])
        return choice, value / total

    def distribution(self):
        counts = self._scores()
        total = sum(counts.values()) or 1
        return {name: counts.get(name, 0) / total for name in ATTACKS}


class Player:
    def __init__(self):
        self.position = pygame.Vector2(280, 390)
        self.radius = 22
        self.speed = 260
        self.health = 100
        self.facing = pygame.Vector2(1, 0)
        self.attack_name = None
        self.attack_timer = 0
        self.attack_cooldown = 0
        self.invulnerable = 0
        self.dodge_cooldown = 0
        self.dodge_timer = 0
        self.attack_power = 1.0
        self.power_name = "None"

    def update(self, dt, keys):
        movement = pygame.Vector2(
            keys[pygame.K_d] - keys[pygame.K_a],
            keys[pygame.K_s] - keys[pygame.K_w],
        )
        if movement.length_squared():
            movement = movement.normalize()
            self.facing = movement
            self.position += movement * self.speed * dt
        self.position.x = clamp(self.position.x, ARENA.left + self.radius, ARENA.right - self.radius)
        self.position.y = clamp(self.position.y, ARENA.top + self.radius, ARENA.bottom - self.radius)
        self.attack_timer = max(0, self.attack_timer - dt)
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        self.dodge_timer = max(0, self.dodge_timer - dt)
        self.dodge_cooldown = max(0, self.dodge_cooldown - dt)

    def dodge(self):
        if self.dodge_cooldown > 0 or self.dodge_timer > 0:
            return False
        self.dodge_timer = 0.28
        self.dodge_cooldown = 1.15
        self.invulnerable = max(self.invulnerable, 0.36)
        self.position += self.facing * 85
        self.position.x = clamp(self.position.x, ARENA.left + self.radius, ARENA.right - self.radius)
        self.position.y = clamp(self.position.y, ARENA.top + self.radius, ARENA.bottom - self.radius)
        return True

    def apply_power(self, power):
        if power == "med_kit":
            self.health = min(100, self.health + 35)
            self.power_name = "Med Kit"
        elif power == "overdrive":
            self.attack_power += 0.35
            self.power_name = "Overdrive"
        elif power == "phase_boots":
            self.speed += 55
            self.dodge_cooldown = 0
            self.power_name = "Phase Boots"

    def attack(self, name):
        if self.attack_cooldown > 0 or self.attack_timer > 0:
            return False
        self.attack_name = name
        self.attack_timer = {"jab": 0.18, "slash": 0.26, "heavy": 0.42}[name]
        self.attack_cooldown = {"jab": 0.32, "slash": 0.48, "heavy": 0.78}[name]
        return True

    def hitbox(self):
        reach = {"jab": 58, "slash": 82, "heavy": 70}.get(self.attack_name, 0)
        width = {"jab": 30, "slash": 52, "heavy": 44}.get(self.attack_name, 0)
        center = self.position + self.facing * reach
        return pygame.Rect(center.x - width, center.y - width, width * 2, width * 2)

    def draw(self, surface):
        color = (150, 210, 255) if self.invulnerable <= 0 else (210, 240, 255)
        if self.dodge_timer > 0:
            pygame.draw.circle(surface, GOLD, self.position, self.radius + 10, 3)
        pygame.draw.circle(surface, color, self.position, self.radius)
        pygame.draw.line(surface, (230, 245, 255), self.position, self.position + self.facing * 35, 5)
        if self.attack_timer > 0:
            box = self.hitbox()
            pygame.draw.ellipse(surface, (100, 190, 255), box, 3)


class Enemy:
    def __init__(self, learner, level=1):
        self.position = pygame.Vector2(720, 390)
        self.radius = 26
        self.level = level
        self.max_health = 100 + (level - 1) * 25
        self.health = self.max_health
        self.learner = learner
        self.mode = "observe"
        self.mode_timer = 0
        self.dodge_cooldown = 0
        self.attack_cooldown = 0
        self.dodge_direction = pygame.Vector2(0, 0)
        self.last_prediction = "slash"
        self.confidence = 0
        self.successes = 0

    def update(self, dt, player):
        self.mode_timer = max(0, self.mode_timer - dt)
        self.dodge_cooldown = max(0, self.dodge_cooldown - dt)
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        to_player = player.position - self.position
        distance = to_player.length() or 1
        direction = to_player.normalize()

        if self.mode_timer <= 0:
            self.choose_action(player, distance, direction)

        if self.mode == "dodge":
            self.position += self.dodge_direction * 390 * dt
        elif self.mode == "attack":
            self.position += direction * 105 * dt
        elif distance > 145:
            self.position += direction * 120 * dt
        elif distance < 95:
            self.position -= direction * 75 * dt

        self.position.x = clamp(self.position.x, ARENA.left + self.radius, ARENA.right - self.radius)
        self.position.y = clamp(self.position.y, ARENA.top + self.radius, ARENA.bottom - self.radius)

    def choose_action(self, player, distance, direction):
        self.last_prediction, self.confidence = self.learner.predict()
        danger = self.last_prediction in ("slash", "heavy")
        player_attacking = player.attack_timer > 0
        learning_bonus = min(0.12, (self.level - 1) * 0.02)

        if danger and self.dodge_cooldown <= 0 and (player_attacking or self.confidence >= 0.42 - learning_bonus) and distance < 250:
            self.mode = "dodge"
            self.mode_timer = 0.42
            self.dodge_cooldown = 1.0
            side = pygame.Vector2(-direction.y, direction.x)
            self.dodge_direction = side if pygame.time.get_ticks() % 2 else -side
            return

        if distance < 150 and self.attack_cooldown <= 0 and (self.confidence >= 0.34 - learning_bonus or player.attack_cooldown > 0.2):
            self.mode = "attack"
            self.mode_timer = 0.36
            self.attack_cooldown = 0.85
            return

        self.mode = "chase"
        self.mode_timer = 0.10

    def draw(self, surface):
        color = RED if self.mode != "dodge" else GOLD
        pygame.draw.circle(surface, color, self.position, self.radius)
        pygame.draw.circle(surface, (255, 220, 220), self.position, self.radius, 3)
        if self.mode == "attack":
            pygame.draw.circle(surface, (255, 145, 145), self.position, 45, 3)
        if self.mode == "dodge":
            pygame.draw.line(surface, (255, 238, 150), self.position - self.dodge_direction * 30, self.position + self.dodge_direction * 30, 5)


def draw_text(surface, font, text, position, color=TEXT):
    surface.blit(font.render(text, True, color), position)


def draw_bar(surface, rect, value, color):
    pygame.draw.rect(surface, (45, 54, 70), rect, border_radius=5)
    fill = rect.copy()
    fill.width = int(rect.width * clamp(value, 0, 1))
    if fill.width:
        pygame.draw.rect(surface, color, fill, border_radius=5)
    pygame.draw.rect(surface, (76, 91, 112), rect, 1, border_radius=5)


def draw_panel(surface, rect, fill=PANEL, outline=(42, 58, 82)):
    pygame.draw.rect(surface, fill, rect, border_radius=10)
    pygame.draw.rect(surface, outline, rect, 2, border_radius=10)


def draw_centered(surface, font, text, y, color=TEXT):
    rendered = font.render(text, True, color)
    surface.blit(rendered, (WIDTH // 2 - rendered.get_width() // 2, y))


def draw_centered_in_rect(surface, font, text, rect, color=TEXT):
    rendered = font.render(text, True, color)
    surface.blit(rendered, (rect.centerx - rendered.get_width() // 2, rect.centery - rendered.get_height() // 2))


def draw_button(surface, font, text, rect, color=BLUE):
    draw_panel(surface, rect, (27, 39, 58), color)
    rendered = font.render(text, True, TEXT)
    surface.blit(rendered, (rect.centerx - rendered.get_width() // 2, rect.centery - rendered.get_height() // 2))


def draw_pill(surface, font, text, position, color):
    rendered = font.render(text, True, color)
    rect = pygame.Rect(position[0], position[1], rendered.get_width() + 18, rendered.get_height() + 8)
    pygame.draw.rect(surface, (24, 34, 49), rect, border_radius=8)
    pygame.draw.rect(surface, color, rect, 1, border_radius=8)
    surface.blit(rendered, (rect.x + 9, rect.y + 4))


def reset_game():
    learner = PatternLearner()
    return Player(), Enemy(learner), learner, "", "menu", 0.0


def main():
    pygame.init()
    pygame.display.set_caption("Adaptive Enemy Arena")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    hero_font = pygame.font.Font(None, 46)
    title_font = pygame.font.Font(None, 30)
    font = pygame.font.Font(None, 23)
    small_font = pygame.font.Font(None, 19)
    player, enemy, learner, message, game_state, enemy_dead_timer = reset_game()
    running = True

    while running:
        dt = min(clock.tick(60) / 1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    player, enemy, learner, message, game_state, enemy_dead_timer = reset_game()
                    game_state = "playing"
                elif event.key == pygame.K_h:
                    game_state = "how_to_play" if game_state != "how_to_play" else "menu"
                elif event.key == pygame.K_p and game_state in ("playing", "paused"):
                    game_state = "paused" if game_state == "playing" else "playing"
                elif game_state == "playing" and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                    if player.dodge():
                        learner.observe("dodge")
                        message = "Player dodged. Enemy recorded the escape pattern."
                elif game_state == "enemy_dead" and event.key in POWER_CHOICES:
                    power, power_name, _ = POWER_CHOICES[event.key]
                    player.apply_power(power)
                    enemy = Enemy(learner, enemy.level + 1)
                    game_state = "playing"
                    message = f"{power_name} equipped. Enemy level {enemy.level} appeared!"
                elif game_state == "menu" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    game_state = "playing"
                elif game_state == "how_to_play" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    game_state = "menu"
                else:
                    attack_name = {pygame.K_q: "jab", pygame.K_SPACE: "slash", pygame.K_e: "heavy"}.get(event.key)
                    if game_state == "playing" and attack_name and player.attack(attack_name):
                        learner.observe(attack_name)
                        message = f"Player used {attack_name}. Enemy updated its model."

        if game_state == "playing":
            keys = pygame.key.get_pressed()
            player.update(dt, keys)
            enemy.update(dt, player)

            if player.attack_timer > 0 and player.attack_name and player.hitbox().collidepoint(enemy.position) and enemy.mode != "dodge":
                damage = {"jab": 5, "slash": 8, "heavy": 14}[player.attack_name]
                enemy.health = max(0, enemy.health - damage * player.attack_power * dt * 10)
            if enemy.mode == "attack" and enemy.position.distance_to(player.position) < 72 and player.invulnerable <= 0:
                player.health = max(0, player.health - 18 * dt)

            if player.health <= 0:
                game_state = "player_dead"
                message = "You died. Press R to restart."
            elif enemy.health <= 0:
                game_state = "enemy_dead"
                enemy_dead_timer = 0.0
                message = f"Enemy level {enemy.level} defeated! Choose a power."

        screen.fill(BG)
        pygame.draw.circle(screen, (18, 31, 50), (WIDTH - 80, 125), 180)
        pygame.draw.circle(screen, (16, 25, 42), (95, HEIGHT - 90), 220)
        pygame.draw.rect(screen, PANEL, (0, 0, WIDTH, 72))
        pygame.draw.rect(screen, (28, 38, 55), ARENA, 2)
        draw_text(screen, title_font, "ADAPTIVE ENEMY ARENA", (28, 18), TEXT)
        draw_text(screen, small_font, "P  pause     H  instructions     R  restart     ESC  quit", (650, 25), MUTED)

        if game_state not in ("menu", "how_to_play"):
            player.draw(screen)
            if game_state != "player_dead" or enemy.health > 0:
                enemy.draw(screen)

        if game_state not in ("menu", "how_to_play"):
            player_card = pygame.Rect(48, 101, 220, 62)
            enemy_card = pygame.Rect(WIDTH - 268, 101, 220, 62)
            draw_panel(screen, player_card, (19, 39, 58), BLUE)
            draw_panel(screen, enemy_card, (52, 27, 40), RED)
            draw_text(screen, small_font, "PLAYER", (62, 111), BLUE)
            draw_text(screen, font, f"{max(0, int(player.health))} HP", (62, 132), TEXT)
            draw_bar(screen, pygame.Rect(135, 134, 115, 10), player.health / 100, BLUE)
            draw_text(screen, small_font, f"ENEMY  LEVEL {enemy.level}", (WIDTH - 254, 111), RED)
            draw_text(screen, font, f"{max(0, int(enemy.health))} HP", (WIDTH - 254, 132), TEXT)
            draw_bar(screen, pygame.Rect(WIDTH - 165, 134, 102, 10), enemy.health / enemy.max_health, RED)
            dodge_ready = player.dodge_cooldown <= 0
            draw_pill(screen, small_font, "DODGE READY" if dodge_ready else f"DODGE {player.dodge_cooldown:.1f}s", (48, 174), GOLD if dodge_ready else MUTED)
            draw_pill(screen, small_font, f"POWER: {player.power_name.upper()}", (WIDTH - 268, 174), GREEN if player.power_name != "None" else MUTED)

        panel = pygame.Rect(32, HEIGHT - 106, WIDTH - 64, 70)
        draw_panel(screen, panel)
        if game_state not in ("menu", "how_to_play"):
            prediction, confidence = learner.predict()
            draw_text(screen, font, f"Enemy decision: {enemy.mode.upper()}", (52, HEIGHT - 91), GOLD if enemy.mode == "dodge" else RED if enemy.mode == "attack" else TEXT)
            draw_text(screen, font, f"Predicted next player attack: {prediction.upper()} ({confidence:.0%})", (280, HEIGHT - 91), TEXT)
            draw_text(screen, small_font, f"Observed actions: {learner.total_attacks}    Power: {player.power_name}", (52, HEIGHT - 62), MUTED)
            if message:
                draw_text(screen, small_font, message, (580, HEIGHT - 62), GREEN)

        if game_state == "menu":
            menu_card = pygame.Rect(250, 155, 500, 390)
            draw_panel(screen, menu_card, (17, 27, 43), (55, 82, 115))
            draw_centered(screen, hero_font, "ADAPTIVE", 205, BLUE)
            draw_centered(screen, hero_font, "ENEMY ARENA", 248, TEXT)
            draw_centered(screen, small_font, "A duel that learns how you fight", 300, MUTED)
            draw_button(screen, font, "ENTER / SPACE   START", pygame.Rect(350, 350, 300, 48), GREEN)
            draw_button(screen, font, "H   HOW TO PLAY", pygame.Rect(350, 412, 300, 48), BLUE)
            draw_centered(screen, small_font, "ESC to quit", 495, MUTED)
        elif game_state == "how_to_play":
            help_card = pygame.Rect(205, 135, 590, 450)
            draw_panel(screen, help_card, (17, 27, 43), (55, 82, 115))
            draw_centered(screen, hero_font, "HOW TO PLAY", 180, TEXT)
            draw_centered(screen, font, "MOVE", 255, BLUE)
            draw_centered(screen, font, "W A S D", 285, TEXT)
            draw_centered(screen, font, "ATTACK", 335, GOLD)
            draw_centered(screen, font, "Q  JAB       SPACE  SLASH       E  HEAVY", 365, TEXT)
            draw_centered(screen, font, "SHIFT  DODGE", 400, GOLD)
            draw_centered(screen, small_font, "The enemy learns your attack patterns and predicts your next move.", 425, MUTED)
            draw_centered(screen, small_font, "Defeat it to choose a power before the next level.", 450, MUTED)
            draw_button(screen, font, "ENTER / SPACE   BACK", pygame.Rect(350, 510, 300, 48), GREEN)
        elif game_state == "enemy_dead":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 12, 22, 170))
            screen.blit(overlay, (0, 0))
            draw_centered(screen, hero_font, "VICTORY", 185, GREEN)
            draw_centered(screen, font, "Choose a superpower for the next level", 245, TEXT)
            for index, (power, power_name, description) in enumerate(POWER_CHOICES.values()):
                card = pygame.Rect(155 + index * 240, 315, 210, 125)
                draw_panel(screen, card, (20, 35, 52), GOLD if index == 1 else BLUE if index == 0 else GREEN)
                draw_centered_in_rect(screen, font, f"{index + 1}  {power_name}", pygame.Rect(card.x, card.y + 12, card.width, 30))
                draw_centered_in_rect(screen, small_font, description, pygame.Rect(card.x, card.y + 68, card.width, 30), MUTED)
            draw_centered(screen, small_font, "Press 1, 2, or 3 to choose. The game is paused until you decide.", 500, MUTED)
        elif game_state == "player_dead":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((35, 5, 16, 185))
            screen.blit(overlay, (0, 0))
            draw_centered(screen, hero_font, "YOU DIED", 280, RED)
            draw_centered(screen, font, "Press R to restart", 335, TEXT)
        elif game_state == "paused":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 12, 22, 185))
            screen.blit(overlay, (0, 0))
            draw_centered(screen, hero_font, "PAUSED", 280, GOLD)
            draw_centered(screen, font, "Press P to resume", 335, TEXT)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
